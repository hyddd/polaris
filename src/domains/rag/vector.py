"""RAGVectorStore — 向量存储封装。"""

import logging
from pathlib import Path

from chromadb import PersistentClient
from chromadb.utils import embedding_functions

from .models import RAGSearchResult

logger = logging.getLogger("polaris.rag.vector")

# 缓存 PersistentClient 实例，避免重复创建
_client_cache: dict[str, PersistentClient] = {}
# 缓存 embedding function 实例
_embedding_function = None


def get_embedding_function():
    global _embedding_function
    if _embedding_function is not None:
        return _embedding_function

    from src.core.config import config

    api_key = config.get("embedding.api_key", "")
    if not api_key:
        raise RuntimeError("未配置 embedding.api_key，向量检索不可用。请在 config/config.local.yaml 中配置。")
    base_url = config.get("embedding.base_url", "")
    model = config.get("embedding.model", "netease-youdao/bce-embedding-base_v1")
    kwargs = {"api_key": api_key, "model_name": model}
    if base_url:
        kwargs["api_base"] = base_url
    _embedding_function = embedding_functions.OpenAIEmbeddingFunction(**kwargs)
    return _embedding_function


def check_embedding_config() -> None:
    """检查 Embedding 配置是否可用，打印配置信息。"""
    from src.core.config import config

    api_key = config.get("embedding.api_key", "")
    model = config.get("embedding.model", "netease-youdao/bce-embedding-base_v1")
    if not api_key:
        print("⚠ 未配置 EMBEDDING_API_KEY，向量检索功能不可用")
        return
    print(f"使用云端 Embedding: {model}")
    if _client_cache or _embedding_function is not None:
        logger.warning("已有缓存的向量存储客户端，若 Embedding 配置发生变更请调用 reset_vector_store_cache() 清空缓存")


def reset_vector_store_cache() -> None:
    """清空客户端和 embedding 缓存，配置变更后调用以强制重建。"""
    global _client_cache, _embedding_function
    _client_cache.clear()
    _embedding_function = None
    logger.warning("向量存储缓存已清空，下次调用将重新创建客户端和 Embedding 函数")


def get_vector_store(persist_dir: str, collection_name: str = "notes"):
    global _client_cache
    if persist_dir not in _client_cache:
        _client_cache[persist_dir] = PersistentClient(path=persist_dir)
    client = _client_cache[persist_dir]
    embedding = get_embedding_function()
    return client.get_or_create_collection(name=collection_name, embedding_function=embedding)


def index_notes(notes_dir: str, persist_dir: str, collection_name: str = "notes") -> None:
    from src.domains.notes.utils import load_notes

    collection = get_vector_store(persist_dir, collection_name)
    notes = load_notes(Path(notes_dir))
    existing_ids = set(collection.get()["ids"])

    for note in notes:
        note_id = note["filename"].replace(".md", "").replace(" ", "-")
        if note_id in existing_ids:
            continue
        collection.add(
            ids=[note_id],
            documents=[note["content"]],
            metadatas=[{
                "title": note["metadata"].get("title", ""),
                "tags": ",".join(note["metadata"].get("tags", [])),
            }],
        )


def add_note_to_index(filename: str, title: str, content: str, tags: list[str],
                      persist_dir: str, collection_name: str = "notes") -> None:
    """Index a single note into the vector store."""
    collection = get_vector_store(persist_dir, collection_name)
    note_id = filename.replace(".md", "").replace(" ", "-")
    # Upsert: update if exists, insert if not
    collection.upsert(
        ids=[note_id],
        documents=[content],
        metadatas=[{"filename": filename, "title": title, "tags": ",".join(tags)}],
    )


def remove_note_from_index(filename: str, persist_dir: str, collection_name: str = "notes") -> None:
    """Remove a note from the vector store."""
    collection = get_vector_store(persist_dir, collection_name)
    note_id = filename.replace(".md", "").replace(" ", "-")
    collection.delete(ids=[note_id])


def search_notes(query: str, persist_dir: str, collection_name: str = "notes", top_k: int = 3) -> list[dict]:
    collection = get_vector_store(persist_dir, collection_name)
    results = collection.query(query_texts=[query], n_results=top_k)
    output = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 0
            output.append({"content": doc, "metadata": meta, "distance": dist})
    return output


class RAGVectorStore:
    """封装向量存储函数调用为类接口。"""

    def __init__(self, persist_dir: str, collection_name: str = "notes"):
        self._persist_dir = persist_dir
        self._collection_name = collection_name

    def add_note(self, filename: str, title: str, content: str,
                 tags: list[str]) -> None:
        """索引或更新单条笔记。"""
        add_note_to_index(filename, title, content, tags,
                          self._persist_dir, self._collection_name)
        logger.debug(f"笔记已索引: {filename}")

    def remove_note(self, filename: str) -> None:
        """从索引移除笔记。"""
        remove_note_from_index(filename, self._persist_dir,
                               self._collection_name)
        logger.debug(f"笔记已从索引移除: {filename}")

    def search(self, query: str, n_results: int = 5) -> list[RAGSearchResult]:
        """语义搜索，返回 RAGSearchResult 列表。"""
        raw = search_notes(query, self._persist_dir,
                           self._collection_name, top_k=n_results)
        results = []
        for item in raw:
            meta = item.get("metadata", {})
            tags_raw = meta.get("tags", "")
            results.append(RAGSearchResult(
                filename=meta.get("filename", ""),
                title=meta.get("title", ""),
                content=item.get("content", ""),
                score=1.0 - item.get("distance", 0.0),
                tags=tags_raw.split(",") if tags_raw else [],
            ))
        return results

    def index_notes(self, notes: list[dict]) -> None:
        """批量索引笔记。notes 元素需含 filename/title/content/tags。"""
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
        col = get_vector_store(self._persist_dir, self._collection_name)
        # 查找该文档的所有 chunk
        results = col.get(where={"doc_id": doc_id})
        if results and results["ids"]:
            col.delete(ids=results["ids"])
            logger.debug(f"文档分块已删除: {doc_id}, {len(results['ids'])} 块")
