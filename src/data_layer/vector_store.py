from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils import embedding_functions


def get_embedding_function():
    import os
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key and api_key not in ("sk-placeholder", "sk-..."):
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key, model_name="text-embedding-3-small"
        )
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


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
