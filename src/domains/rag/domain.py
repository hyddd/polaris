"""RAGDomain — 语义检索核心服务。"""

import logging
import threading

from src.core.events import event_bus
from src.domains.notes.models import SearchResult
from .chunker import TextChunker
from .vector import RAGVectorStore

logger = logging.getLogger("polaris.rag")


class RAGDomain:
    """语义检索领域服务，提供向量索引和语义搜索能力。"""

    def __init__(self, store: RAGVectorStore, chunker: TextChunker | None = None):
        self._store = store
        self._chunker = chunker or TextChunker()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
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
    store = RAGVectorStore(persist_dir=persist_dir, collection_name="notes")
    global _domain
    _domain = RAGDomain(store)
    logger.info("RAG 域已初始化")


event_bus.subscribe("app:startup", _on_startup)
