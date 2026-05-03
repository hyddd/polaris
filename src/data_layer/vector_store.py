import logging
from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# 缓存 PersistentClient 实例，避免重复创建
_client_cache: dict[str, PersistentClient] = {}
# 缓存 embedding function 实例
_embedding_function = None


def get_embedding_function():
    global _embedding_function
    if _embedding_function is not None:
        return _embedding_function

    from src.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL

    api_key = EMBEDDING_API_KEY
    if not api_key:
        raise RuntimeError("未配置 EMBEDDING_API_KEY，向量检索不可用。请在 .env 中配置硅基流动 API。")
    base_url = EMBEDDING_BASE_URL
    model = EMBEDDING_MODEL
    kwargs = {"api_key": api_key, "model_name": model}
    if base_url:
        kwargs["api_base"] = base_url
    _embedding_function = embedding_functions.OpenAIEmbeddingFunction(**kwargs)
    return _embedding_function


def check_embedding_config() -> None:
    """检查 Embedding 配置是否可用，打印配置信息。"""
    from src.config import EMBEDDING_API_KEY, EMBEDDING_MODEL

    if not EMBEDDING_API_KEY:
        print("⚠ 未配置 EMBEDDING_API_KEY，向量检索功能不可用")
        return
    print(f"使用云端 Embedding: {EMBEDDING_MODEL}")
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
    from src.data_layer.loader import load_notes

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
        metadatas=[{"title": title, "tags": ",".join(tags)}],
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
