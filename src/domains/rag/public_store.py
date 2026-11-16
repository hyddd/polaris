"""知识库文档记录的存储，以及 personal 访问 team 知识库的客户端。

文档的向量都在本机 Chroma（team 服务的 Chroma 里就是公共数据），这里只管"有哪些文档"的记录：
- JsonDocMeta：personal 的私人文档，存 data/knowledge_meta.json；
- PublicDocMeta：team 的公共文档，存 MySQL knowledge_documents 表；
- RemoteKnowledge：personal 读写公共文档和检索公共知识，调 team 服务的 /api/knowledge 接口。
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.db import PUBLIC, PRIVATE
from src.core.db.public_store import PublicStoreBase, dump_list, load_list, now
from src.core.db.remote import RemoteError, get_remote
from .models import RAGSearchResult

logger = logging.getLogger("polaris.rag.store")


class JsonDocMeta:
    scope = PRIVATE

    def __init__(self, path: Path):
        self._path = Path(path)

    def list_docs(self) -> list[dict]:
        if self._path.exists():
            try:
                return [{**m, "scope": self.scope} for m in json.loads(self._path.read_text())]
            except Exception as e:
                logger.warning(f"加载文档元数据失败: {e}")
        return []

    def _write(self, meta: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([{k: v for k, v in m.items() if k != "scope"} for m in meta],
                                         ensure_ascii=False, indent=2))

    def add(self, doc_id: str, filename: str, chunk_count: int, tags: list[str]) -> None:
        meta = self.list_docs()
        meta.append({"doc_id": doc_id, "filename": filename, "chunk_count": chunk_count,
                     "tags": tags, "created_at": datetime.now().isoformat()})
        self._write(meta)

    def has(self, doc_id: str) -> bool:
        return any(m["doc_id"] == doc_id for m in self.list_docs())

    def remove(self, doc_id: str) -> bool:
        meta = self.list_docs()
        keep = [m for m in meta if m["doc_id"] != doc_id]
        if len(keep) < len(meta):
            self._write(keep)
            return True
        return False


class PublicDocMeta(PublicStoreBase):
    scope = PUBLIC

    def list_docs(self) -> list[dict]:
        db = self.db()
        rows = db.fetchall(f"SELECT * FROM {db.t('knowledge_documents')} ORDER BY created_at")
        return [{"doc_id": r["doc_id"], "filename": r["filename"], "chunk_count": int(r["chunk_count"]),
                 "tags": load_list(r["tags"]), "created_at": r["created_at"].isoformat(), "scope": PUBLIC}
                for r in rows]

    def add(self, doc_id: str, filename: str, chunk_count: int, tags: list[str]) -> None:
        db = self.db()
        db.execute(f"INSERT INTO {db.t('knowledge_documents')} (doc_id, filename, chunk_count, tags, created_at) "
                   f"VALUES (%s,%s,%s,%s,%s)", (doc_id, filename, chunk_count, dump_list(tags), now()))

    def has(self, doc_id: str) -> bool:
        db = self.db()
        return db.fetchone(f"SELECT doc_id FROM {db.t('knowledge_documents')} WHERE doc_id=%s", (doc_id,)) is not None

    def remove(self, doc_id: str) -> bool:
        db = self.db()
        return db.execute(f"DELETE FROM {db.t('knowledge_documents')} WHERE doc_id=%s", (doc_id,)) > 0


class RemoteKnowledge:
    """personal → team：公共知识库（文档 + 公共笔记的检索）。"""

    def __init__(self, client_getter=get_remote):
        self._client_getter = client_getter

    def _c(self):
        c = self._client_getter()
        if c is None:
            raise RemoteError("没有连接团队服务")
        return c

    def search(self, query: str, top_k: int = 5) -> list[RAGSearchResult]:
        items = self._c().get("/api/knowledge/search", params={"q": query, "top_k": top_k}).get("items", [])
        return [RAGSearchResult(filename=d.get("filename", ""), title=d.get("title", ""),
                                content=d.get("content", ""), score=float(d.get("score", 0.0)),
                                tags=d.get("tags", []), scope=PUBLIC) for d in items]

    def list_docs(self) -> list[dict]:
        return [{**d, "scope": PUBLIC} for d in self._c().get("/api/knowledge").get("items", [])]

    def upload(self, filename: str, data: bytes) -> dict:
        r = self._c().post("/api/knowledge/upload", params={"scope": PUBLIC}, files={"file": (filename, data)})
        return {**r, "scope": PUBLIC}

    def delete(self, doc_id: str) -> bool:
        try:
            self._c().delete(f"/api/knowledge/{doc_id}")
            return True
        except RemoteError as e:
            if e.status == 404:
                return False
            raise
