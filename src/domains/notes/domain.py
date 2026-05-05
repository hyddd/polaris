"""NotesDomain — 笔记管理核心服务。"""

import logging
import threading

from src.core.infra import event_bus
from .models import Note, SearchResult
from .store import NoteStore

logger = logging.getLogger("polaris.notes")


class NotesDomain:
    def __init__(self, store: NoteStore, persist_dir: str = "",
                 collection_name: str = "notes"):
        self._store = store
        self._persist_dir = persist_dir
        self._collection_name = collection_name

    # ------------------------------------------------------------------
    # 向量索引联动
    # ------------------------------------------------------------------

    def _async_index(self, filename: str, title: str, content: str,
                     tags: list[str]) -> None:
        """后台异步将笔记加入向量索引。"""
        if not self._persist_dir:
            return
        def _work():
            try:
                from src.domains.rag.vector import add_note_to_index
                add_note_to_index(filename, title, content, tags,
                                  self._persist_dir, self._collection_name)
                logger.debug(f"笔记已索引: {filename}")
            except Exception as e:
                logger.warning(f"笔记索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _async_deindex(self, filename: str) -> None:
        """后台异步从向量索引移除笔记。"""
        if not self._persist_dir:
            return
        def _work():
            try:
                from src.domains.rag.vector import remove_note_from_index
                remove_note_from_index(filename, self._persist_dir,
                                       self._collection_name)
                logger.debug(f"笔记已从索引移除: {filename}")
            except Exception as e:
                logger.warning(f"笔记移除索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_notes(self, tag: str | None = None) -> list[Note]:
        """列出所有笔记，可按标签筛选。"""
        return self._store.list_notes(tag=tag)

    def get_note(self, filename: str) -> Note | None:
        """按文件名获取笔记。"""
        return self._store.get_note(filename)

    def search(self, keyword: str) -> list[SearchResult]:
        """语义搜索笔记，委托给向量检索。"""
        if not self._persist_dir:
            logger.warning("向量存储未配置，回退到关键词搜索")
            notes = self._store.search_content(keyword)
            return [
                SearchResult(
                    filename=n.filename, title=n.title,
                    content=n.content, score=0.0, tags=n.tags,
                )
                for n in notes
            ]
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
                ))
            return results
        except Exception as e:
            logger.warning(f"向量搜索失败，回退到关键词搜索: {e}")
            notes = self._store.search_content(keyword)
            return [
                SearchResult(
                    filename=n.filename, title=n.title,
                    content=n.content, score=0.0, tags=n.tags,
                )
                for n in notes
            ]

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def create_note(self, title: str, content: str = "",
                    tags: list[str] | None = None,
                    channel: str = "admin",
                    session_id: str = "") -> Note:
        """创建笔记。"""
        note = self._store.create_note(title, content, tags)
        self._async_index(note.filename, note.title, note.content, note.tags)
        event_bus.publish("notes:note_created",
                          note_id=note.filename, title=note.title,
                          tags=note.tags,
                          channel=channel, session_id=session_id)
        return note

    def update_note(self, filename: str, content: str | None = None,
                    tags: list[str] | None = None) -> Note | None:
        """更新笔记。"""
        note = self._store.update_note(filename, content, tags)
        if note:
            self._async_index(note.filename, note.title, note.content, note.tags)
            event_bus.publish("notes:note_updated",
                              note_id=note.filename, title=note.title,
                              tags=note.tags)
        return note

    def delete_note(self, filename: str) -> bool:
        """删除笔记。"""
        deleted = self._store.delete_note(filename)
        if deleted:
            self._async_deindex(filename)
            event_bus.publish("notes:note_deleted", note_id=filename)
        return deleted

    def archive_note(self, filename: str) -> bool:
        """归档笔记。"""
        archived = self._store.archive_note(filename)
        if archived:
            self._async_deindex(filename)
            event_bus.publish("notes:note_deleted", note_id=filename)
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
    notes_dir = config.resolve_path(config.get("storage.notes_dir", "data/notes"))
    persist_dir = str(config.resolve_path(
        config.get("storage.vector_db_dir", "data/chroma")))
    store = NoteStore(
        notes_dir=str(notes_dir),
        archive_dir=str(notes_dir / "archive"),
    )
    global _domain
    _domain = NotesDomain(store, persist_dir=persist_dir)
    logger.info("笔记域已初始化")


event_bus.subscribe("app:startup", _on_startup)
