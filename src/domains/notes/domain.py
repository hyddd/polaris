"""NotesDomain — 笔记管理核心服务。

本机笔记的向量在本机 Chroma（personal：私人 .md 笔记；team：MySQL 里的公共笔记）。
personal 的公共笔记交给 team 服务检索，两边结果按名次融合（RRF）后返回。
"""

import logging

from src.core.infra import event_bus
from .models import Note, SearchResult
from .store import NoteStore

logger = logging.getLogger("polaris.notes")


class NotesDomain:
    def __init__(self, store: NoteStore, persist_dir: str = "",
                 collection_name: str = "notes", local_scope: str = "private"):
        """local_scope：本机 Chroma 里的笔记是哪类（team 服务是 public）。"""
        self._store = store
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._local_scope = local_scope

    @property
    def public_error(self) -> str | None:
        return getattr(self._store, "public_error", None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_notes(self, tag: str | None = None) -> list[Note]:
        """列出所有笔记（本机私有 + 公共），可按标签筛选。"""
        return self._store.list_notes(tag=tag)

    def get_note(self, filename: str) -> Note | None:
        """按文件名获取笔记。"""
        return self._store.get_note(filename)

    def search(self, keyword: str, top_k: int = 5) -> list[SearchResult]:
        """语义搜索：本机（Chroma）+（personal）team 服务的公共笔记，按名次融合。"""
        local = self._search_local(keyword)
        public = self._search_remote(keyword, top_k)
        if not public:
            return local
        if not local:
            return public[:top_k]
        from src.domains.rag.merge import rrf_merge
        merged = rrf_merge([local, public], top_k=top_k,
                           key=lambda r: (r.scope, r.filename, r.title, r.content[:50]))
        # 只用融合分数排序；每条保留自己来源的相关度（工具按相关度过滤，融合分数尺度太小）
        return [item for item, _ in merged]

    def _keyword_fallback(self, keyword: str) -> list[SearchResult]:
        notes = self._store.search_content(keyword)
        return [SearchResult(filename=n.filename, title=n.title, content=n.content,
                             score=0.0, tags=n.tags, scope=n.scope) for n in notes]

    def _search_local(self, keyword: str) -> list[SearchResult]:
        local = self._local_scope
        if not self._persist_dir:
            logger.warning("向量存储未配置，回退到关键词搜索")
            return [r for r in self._keyword_fallback(keyword) if r.scope == local]
        try:
            from src.domains.rag.vector import search_notes
            raw = search_notes(keyword, self._persist_dir,
                               self._collection_name)
            results = []
            for item in raw:
                meta = item.get("metadata", {})
                results.append(SearchResult(
                    filename=meta.get("filename", ""),
                    title=meta.get("title", ""),
                    content=item.get("content", ""),
                    score=1.0 - item.get("distance", 0.0),
                    tags=meta.get("tags", "").split(",") if meta.get("tags") else [],
                    scope=local,
                ))
            return results
        except Exception as e:
            logger.warning(f"本机向量搜索失败，回退到关键词搜索: {e}")
            return [r for r in self._keyword_fallback(keyword) if r.scope == local]

    def _search_remote(self, keyword: str, top_k: int) -> list[SearchResult]:
        fn = getattr(self._store, "semantic_search_public", None)
        results = fn(keyword, top_k) if fn else None
        return results or []

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def create_note(self, title: str, content: str = "",
                    tags: list[str] | None = None,
                    channel: str = "admin",
                    session_id: str = "", scope: str | None = None) -> Note:
        """创建笔记。scope：public 存公共库、private 存本机；不传用默认。"""
        from src.core.db import resolve_scope
        scope = resolve_scope(scope)
        if hasattr(self._store, "scope_of"):
            note = self._store.create_note(title, content, tags, scope=scope)
        else:
            note = self._store.create_note(title, content, tags)
        # 带上 content 和 scope：存在本机的笔记由 RAG 域写进本机 Chroma（personal 的公共笔记由团队服务自己索引）
        event_bus.publish("notes:note_created",
                          note_id=note.filename, title=note.title,
                          content=note.content, tags=note.tags, scope=note.scope,
                          channel=channel, session_id=session_id)
        return note

    def update_note(self, filename: str, content: str | None = None,
                    tags: list[str] | None = None) -> Note | None:
        """更新笔记。"""
        note = self._store.update_note(filename, content, tags)
        if note:
            event_bus.publish("notes:note_updated",
                              note_id=note.filename, title=note.title,
                              content=note.content, tags=note.tags, scope=note.scope)
        return note

    def _scope_of(self, filename: str) -> str:
        if hasattr(self._store, "scope_of"):
            return self._store.scope_of(filename) or "private"
        return "private"

    def delete_note(self, filename: str) -> bool:
        """删除笔记。"""
        scope = self._scope_of(filename)
        deleted = self._store.delete_note(filename)
        if deleted:
            event_bus.publish("notes:note_deleted", note_id=filename, scope=scope)
        return deleted

    def archive_note(self, filename: str) -> bool:
        """归档笔记。"""
        scope = self._scope_of(filename)
        archived = self._store.archive_note(filename)
        if archived:
            event_bus.publish("notes:note_deleted", note_id=filename, scope=scope)
        return archived


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: NotesDomain | None = None


def get_notes_domain() -> NotesDomain:
    return _domain


def set_notes_domain(domain: NotesDomain | None):
    global _domain
    _domain = domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(**kwargs):
    from src.core.config import config
    from src.core.db import is_team, public_enabled, instance_info, PUBLIC, PRIVATE
    from src.core.db.public_store import NoPrivate
    from src.domains.rag import vector_collection
    from .public_store import PublicNoteStore, RemoteNoteStore, ScopedNoteStore
    persist_dir = str(config.resolve_path(
        config.get("storage.vector_db_dir", "data/chroma")))
    if is_team():
        store = ScopedNoteStore(NoPrivate(), PublicNoteStore() if public_enabled() else None)
    else:
        notes_dir = config.resolve_path(config.get("storage.notes_dir", "data/notes"))
        private = NoteStore(notes_dir=str(notes_dir), archive_dir=str(notes_dir / "archive"))
        store = ScopedNoteStore(private, RemoteNoteStore() if public_enabled() else None)
    global _domain
    _domain = NotesDomain(store, persist_dir=persist_dir, collection_name=vector_collection(),
                          local_scope=PUBLIC if is_team() else PRIVATE)
    logger.info(f"笔记域已初始化（{instance_info()['mode_label']}，公共数据{'可用' if public_enabled() else '未启用'}）")


event_bus.subscribe("app:startup", _on_startup)
