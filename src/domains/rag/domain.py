"""RAGDomain — 语义检索核心服务。

向量都在本机 Chroma：personal 的 Chroma 里是私人数据，team 的 Chroma 里是公共数据（local_scope）。
personal 的公共知识通过 HTTP 找 team 服务检索/上传/删除（remote），两边结果按名次融合。
"""

import logging
import threading
import uuid
from pathlib import Path

from src.core.infra import event_bus
from .models import RAGSearchResult
from .chunker import TextChunker
from .vector import RAGVectorStore
from .merge import rrf_merge
from .public_store import JsonDocMeta

logger = logging.getLogger("polaris.rag")


class RAGDomain:
    """语义检索领域服务，提供向量索引和语义搜索能力。"""

    def __init__(self, store: RAGVectorStore, chunker: TextChunker | None = None,
                 meta_path: Path | None = None, doc_meta=None, remote=None):
        """store：本机 Chroma；doc_meta：本机文档记录（默认 JSON 文件，team 用 MySQL）；
        remote：personal 访问 team 公共知识库的客户端，没连 team 时为 None。"""
        self._store = store
        self._chunker = chunker or TextChunker()
        self._docs = doc_meta or JsonDocMeta(meta_path or Path("data/knowledge_meta.json"))
        self.local_scope = self._docs.scope
        self._remote = remote
        self.public_error: str | None = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def _remote_call(self, fn, default):
        """读 team 服务：连不上时只返回本机数据，并记下原因。"""
        from src.core.db import DatabaseError
        if self._remote is None:
            return default
        try:
            result = fn()
            self.public_error = None
            return result
        except DatabaseError as e:
            self.public_error = str(e)
            logger.warning(f"团队服务读取失败，只显示私人数据：{e}")
            return default

    def search(self, query: str, top_k: int = 5) -> list[RAGSearchResult]:
        """语义搜索：本机 Chroma +（personal）team 服务的公共知识，按名次融合（两边分数尺度不同）。"""
        local = []
        try:
            local = self._store.search(query, n_results=top_k)
            for r in local:
                r.scope = self.local_scope
        except Exception as e:
            logger.warning(f"本机向量搜索失败: {e}")
        public = self._remote_call(lambda: self._remote.search(query, top_k=top_k), [])
        if not public or not local:
            return (local or public)[:top_k]
        merged = rrf_merge([local, public], top_k=top_k,
                           key=lambda r: (r.scope, r.filename, r.title, r.content[:50]))
        # 只用融合分数排序；每条保留自己来源的相关度（工具按相关度过滤，融合分数尺度太小）
        return [item for item, _ in merged]

    def index_note(self, filename: str, title: str, content: str,
                   tags: list[str]) -> None:
        """索引单条笔记。"""
        self._store.add_note(filename, title, content, tags)

    def remove_note(self, filename: str) -> None:
        """移除笔记索引。"""
        self._store.remove_note(filename)

    def index_notes(self, notes: list[dict]) -> None:
        """批量索引笔记。"""
        self._store.index_notes(notes)

    def upload_document(self, file_path: str = None, file_data: bytes = None,
                       filename: str = "", tags: list[str] = None, scope: str | None = None) -> dict | None:
        """上传并索引文档。

        Args:
            file_path: 文件路径（本地文件）
            file_data: 文件 bytes 数据（上传文件）
            filename: 文件名
            tags: 标签
            scope: public / private，不传用默认

        Returns:
            {"doc_id": str, "filename": str, "chunk_count": int, "scope": str}
        """
        from src.core.db import resolve_scope
        from .parser import DocumentParser

        scope = resolve_scope(scope)
        if file_path:
            filename = filename or Path(file_path).name
        if scope != self.local_scope:
            # personal 上传公共文档：原文件交给 team 服务解析、索引
            if file_path:
                file_data = Path(file_path).read_bytes()
            if not file_data:
                return None
            if self._remote is None:
                raise RuntimeError("没有连接团队服务，不能上传公共文档")
            result = self._remote.upload(filename, file_data)
            event_bus.publish("rag:document_indexed", doc_id=result.get("doc_id"), filename=filename,
                              chunk_count=result.get("chunk_count", 0), scope=scope)
            return result

        parser = DocumentParser()
        if file_path:
            text = parser.parse_file(file_path)
        elif file_data:
            text = parser.parse_bytes(file_data, filename)
        else:
            return None

        if not text:
            return None

        # 分块
        chunks = self._chunker.chunk(text, metadata={"filename": filename, "tags": tags or []})

        # 生成文档 ID
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # 向量化索引（Chroma），再保存文档记录
        self._store.index_chunks(doc_id, chunks)
        self._docs.add(doc_id, filename, len(chunks), tags or [])

        event_bus.publish("rag:document_indexed",
                          doc_id=doc_id, filename=filename, chunk_count=len(chunks), scope=scope)
        return {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks), "scope": scope}

    def list_documents(self) -> list[dict]:
        """列出所有已索引的文档（本机 +（personal）team 的公共文档），每项带 scope。"""
        return self._docs.list_docs() + self._remote_call(self._remote.list_docs if self._remote else None, [])

    def delete_document(self, doc_id: str) -> bool:
        """删除文档及其向量索引。"""
        if self._docs.has(doc_id):
            self._store.remove_chunks(doc_id)
            removed = self._docs.remove(doc_id)
        elif self._remote is not None:
            removed = self._remote.delete(doc_id)
        else:
            removed = False
        if removed:
            event_bus.publish("rag:document_removed", doc_id=doc_id)
        return removed

    # ------------------------------------------------------------------
    # 后台任务
    # ------------------------------------------------------------------

    def _async_index(self, filename: str, title: str, content: str,
                     tags: list[str], scope: str = "private") -> None:
        """后台异步索引笔记。只索引存在本机的笔记：personal 的公共笔记由 team 服务自己索引。"""
        if scope != self.local_scope:
            return

        def _work():
            try:
                self.index_note(filename, title, content, tags)
                logger.debug(f"笔记已索引（{scope}）: {filename}")
            except Exception as e:
                logger.warning(f"笔记索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _async_remove(self, filename: str, scope: str = "private") -> None:
        """后台异步移除索引。"""
        if scope != self.local_scope:
            return

        def _work():
            try:
                self.remove_note(filename)
                logger.debug(f"笔记已从索引移除（{scope}）: {filename}")
            except Exception as e:
                logger.warning(f"笔记移除索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: RAGDomain | None = None


def vector_collection() -> str:
    """本机 Chroma 的集合名。team 和 personal 分开：personal 改成 team 模式时，原来的私人向量不会被当成公共数据检索出来。"""
    from src.core.db import is_team
    return "public" if is_team() else "notes"


def get_rag_domain() -> RAGDomain | None:
    return _domain


# ---------------------------------------------------------------------------
# 事件订阅：笔记变更自动同步向量索引
# ---------------------------------------------------------------------------

def _on_note_created(note_id=None, title=None, content=None, tags=None,
                     scope="private", **kwargs):
    domain = get_rag_domain()
    if domain and content:
        domain._async_index(note_id, title or "", content, tags or [], scope or "private")


def _on_note_updated(note_id=None, title=None, content=None, tags=None,
                     scope="private", **kwargs):
    domain = get_rag_domain()
    if domain and content:
        domain._async_index(note_id, title or "", content, tags or [], scope or "private")


def _on_note_deleted(note_id=None, scope="private", **kwargs):
    domain = get_rag_domain()
    if domain and note_id:
        domain._async_remove(note_id, scope or "private")


event_bus.subscribe("notes:note_created", _on_note_created)
event_bus.subscribe("notes:note_updated", _on_note_updated)
event_bus.subscribe("notes:note_deleted", _on_note_deleted)


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------

def _on_startup(**kwargs):
    from src.core.config import config
    from src.core.db import is_team, public_enabled, instance_info
    from .public_store import PublicDocMeta, RemoteKnowledge
    persist_dir = str(config.resolve_path(
        config.get("storage.vector_db_dir", "data/chroma")))
    store = RAGVectorStore(persist_dir=persist_dir, collection_name=vector_collection())
    if is_team():
        # 团队服务：本机 Chroma 存公共向量，文档记录存 MySQL（没配数据库时读写都会报"公共库未启用"）
        doc_meta, remote = PublicDocMeta(), None
    else:
        doc_meta = JsonDocMeta(config.resolve_path("data/knowledge_meta.json"))
        remote = RemoteKnowledge() if public_enabled() else None
    global _domain
    _domain = RAGDomain(store, doc_meta=doc_meta, remote=remote)
    logger.info(f"RAG 域已初始化（{instance_info()['mode_label']}）")


event_bus.subscribe("app:startup", _on_startup)
