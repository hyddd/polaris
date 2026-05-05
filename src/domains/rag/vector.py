"""RAGVectorStore — 向量存储封装，复用 src.storage.vector。"""

import logging

from src.domains.notes.models import SearchResult

logger = logging.getLogger("polaris.rag.vector")


class RAGVectorStore:
    """封装 src.storage.vector 的函数调用为类接口。"""

    def __init__(self, persist_dir: str, collection_name: str = "notes"):
        self._persist_dir = persist_dir
        self._collection_name = collection_name

    def add_note(self, filename: str, title: str, content: str,
                 tags: list[str]) -> None:
        """索引或更新单条笔记。"""
        from src.storage.vector import add_note_to_index
        add_note_to_index(filename, title, content, tags,
                          self._persist_dir, self._collection_name)
        logger.debug(f"笔记已索引: {filename}")

    def remove_note(self, filename: str) -> None:
        """从索引移除笔记。"""
        from src.storage.vector import remove_note_from_index
        remove_note_from_index(filename, self._persist_dir,
                               self._collection_name)
        logger.debug(f"笔记已从索引移除: {filename}")

    def search(self, query: str, n_results: int = 5) -> list[SearchResult]:
        """语义搜索，返回 SearchResult 列表。"""
        from src.storage.vector import search_notes
        raw = search_notes(query, self._persist_dir,
                           self._collection_name, top_k=n_results)
        results = []
        for item in raw:
            meta = item.get("metadata", {})
            tags_raw = meta.get("tags", "")
            results.append(SearchResult(
                filename=meta.get("filename", ""),
                title=meta.get("title", ""),
                content=item.get("content", ""),
                score=1.0 - item.get("distance", 0.0),
                tags=tags_raw.split(",") if tags_raw else [],
            ))
        return results

    def index_notes(self, notes: list[dict]) -> None:
        """批量索引笔记。notes 元素需含 filename/title/content/tags。"""
        from src.storage.vector import add_note_to_index
        for note in notes:
            try:
                add_note_to_index(
                    filename=note["filename"],
                    title=note.get("title", ""),
                    content=note.get("content", ""),
                    tags=note.get("tags", []),
                    persist_dir=self._persist_dir,
                    collection_name=self._collection_name,
                )
            except Exception as e:
                logger.warning(f"批量索引失败 ({note.get('filename', '?')}): {e}")
        logger.info(f"批量索引完成: {len(notes)} 条")

    def index_chunks(self, doc_id: str, chunks: list[dict]) -> None:
        """索引文档的所有分块。"""
        from src.storage.vector import get_vector_store
        col = get_vector_store(self._persist_dir, self._collection_name)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{i}"
            col.upsert(
                ids=[chunk_id],
                documents=[chunk["content"]],
                metadatas=[{**chunk.get("metadata", {}), "doc_id": doc_id, "chunk_index": i}],
            )
        logger.debug(f"文档分块已索引: {doc_id}, {len(chunks)} 块")

    def remove_chunks(self, doc_id: str) -> None:
        """删除文档的所有分块。"""
        from src.storage.vector import get_vector_store
        col = get_vector_store(self._persist_dir, self._collection_name)
        # 查找该文档的所有 chunk
        results = col.get(where={"doc_id": doc_id})
        if results and results["ids"]:
            col.delete(ids=results["ids"])
            logger.debug(f"文档分块已删除: {doc_id}, {len(results['ids'])} 块")
