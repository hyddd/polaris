import os
from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils import embedding_functions


def get_embedding_function():
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    if not api_key:
        raise RuntimeError("未配置 EMBEDDING_API_KEY，向量检索不可用。请在 .env 中配置硅基流动 API。")
    base_url = os.getenv("EMBEDDING_BASE_URL", "")
    model = os.getenv("EMBEDDING_MODEL", "netease-youdao/bce-embedding-base_v1")
    kwargs = {"api_key": api_key, "model_name": model}
    if base_url:
        kwargs["api_base"] = base_url
    return embedding_functions.OpenAIEmbeddingFunction(**kwargs)


def prewarm_embedding_model() -> None:
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    if not api_key:
        print("⚠ 未配置 EMBEDDING_API_KEY，向量检索功能不可用")
        return
    print(f"使用云端 Embedding: {os.getenv('EMBEDDING_MODEL', 'netease-youdao/bce-embedding-base_v1')}")


def get_vector_store(persist_dir: str, collection_name: str = "notes"):
    client = PersistentClient(path=persist_dir)
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
