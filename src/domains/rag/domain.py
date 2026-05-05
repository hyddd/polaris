"""RAGDomain — 语义检索核心服务。"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from src.core.infra import event_bus
from .models import RAGSearchResult
from .chunker import TextChunker
from .vector import RAGVectorStore

logger = logging.getLogger("polaris.rag")


class RAGDomain:
    """语义检索领域服务，提供向量索引和语义搜索能力。"""

    def __init__(self, store: RAGVectorStore, chunker: TextChunker | None = None,
                 meta_path: Path | None = None):
        self._store = store
        self._chunker = chunker or TextChunker()
        self._meta_path = meta_path or Path("data/knowledge_meta.json")

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[RAGSearchResult]:
        """语义搜索笔记。"""
        return self._store.search(query, n_results=top_k)

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
                       filename: str = "", tags: list[str] = None) -> dict | None:
        """上传并索引文档。

        Args:
            file_path: 文件路径（本地文件）
            file_data: 文件 bytes 数据（上传文件）
            filename: 文件名
            tags: 标签

        Returns:
            {"doc_id": str, "filename": str, "chunk_count": int}
        """
        from .parser import DocumentParser

        parser = DocumentParser()

        if file_path:
            text = parser.parse_file(file_path)
            filename = filename or Path(file_path).name
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

        # 向量化索引
        self._store.index_chunks(doc_id, chunks)

        # 保存元数据
        self._save_doc_meta(doc_id, filename, len(chunks), tags or [])

        return {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks)}

    def list_documents(self) -> list[dict]:
        """列出所有已索引的文档。"""
        return self._load_doc_meta()

    def delete_document(self, doc_id: str) -> bool:
        """删除文档及其向量索引。"""
        self._store.remove_chunks(doc_id)
        return self._remove_doc_meta(doc_id)

    # ------------------------------------------------------------------
    # 文档元数据管理
    # ------------------------------------------------------------------

    def _save_doc_meta(self, doc_id: str, filename: str, chunk_count: int, tags: list[str]) -> None:
        """保存文档元数据到 JSON 文件。"""
        meta = self._load_doc_meta()
        meta.append({
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": chunk_count,
            "tags": tags,
            "created_at": datetime.now().isoformat(),
        })
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def _load_doc_meta(self) -> list[dict]:
        """加载文档元数据。"""
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text())
            except Exception as e:
                logger.warning(f"加载文档元数据失败: {e}")
        return []

    def _remove_doc_meta(self, doc_id: str) -> bool:
        """删除文档元数据。"""
        meta = self._load_doc_meta()
        before = len(meta)
        meta = [m for m in meta if m["doc_id"] != doc_id]
        if len(meta) < before:
            self._meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
            return True
        return False

    # ------------------------------------------------------------------
    # 后台任务
    # ------------------------------------------------------------------

    def _async_index(self, filename: str, title: str, content: str,
                     tags: list[str]) -> None:
        """后台异步索引笔记。"""
        def _work():
            try:
                self.index_note(filename, title, content, tags)
                logger.debug(f"笔记已索引: {filename}")
            except Exception as e:
                logger.warning(f"笔记索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _async_remove(self, filename: str) -> None:
        """后台异步移除索引。"""
        def _work():
            try:
                self.remove_note(filename)
                logger.debug(f"笔记已从索引移除: {filename}")
            except Exception as e:
                logger.warning(f"笔记移除索引失败 ({filename}): {e}")
        threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: RAGDomain | None = None


def get_rag_domain() -> RAGDomain | None:
    return _domain


# ---------------------------------------------------------------------------
# 事件订阅：笔记变更自动同步向量索引
# ---------------------------------------------------------------------------

def _on_note_created(note_id=None, title=None, content=None, tags=None,
                     **kwargs):
    domain = get_rag_domain()
    if domain and content:
        domain._async_index(note_id, title or "", content, tags or [])


def _on_note_updated(note_id=None, title=None, content=None, tags=None,
                     **kwargs):
    domain = get_rag_domain()
    if domain and content:
        domain._async_index(note_id, title or "", content, tags or [])


def _on_note_deleted(note_id=None, **kwargs):
    domain = get_rag_domain()
    if domain and note_id:
        domain._async_remove(note_id)


event_bus.subscribe("notes:note_created", _on_note_created)
event_bus.subscribe("notes:note_updated", _on_note_updated)
event_bus.subscribe("notes:note_deleted", _on_note_deleted)


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------

def _on_startup(**kwargs):
    from src.core.config import config
    persist_dir = str(config.resolve_path(
        config.get("storage.vector_db_dir", "data/chroma")))
    meta_path = config.resolve_path("data/knowledge_meta.json")
    store = RAGVectorStore(persist_dir=persist_dir, collection_name="notes")
    global _domain
    _domain = RAGDomain(store, meta_path=meta_path)
    logger.info("RAG 域已初始化")


event_bus.subscribe("app:startup", _on_startup)
