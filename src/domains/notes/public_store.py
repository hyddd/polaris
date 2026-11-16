"""笔记的公共存储和公私组合存储。

- PublicNoteStore：team 服务用，正文存 MySQL；向量由 team 的 RAG 域写进 team 本机的 Chroma；
- RemoteNoteStore：personal 服务用，调 team 服务的 /api/notes 接口（语义检索也交给 team）；
- ScopedNoteStore：组合存储，team 模式私人一侧是 NoPrivate。
"""
import logging
import re
import uuid
from datetime import date

from src.core.db import PUBLIC, PRIVATE
from src.core.db.public_store import PublicStoreBase, MergedReadMixin, dump_list, load_list, date_str, now
from src.core.db.remote import RemoteError, get_remote
from .models import Note, SearchResult
from .store import NoteStore

logger = logging.getLogger("polaris.notes.public")


class RemoteNoteStore:
    """personal → team：公共笔记通过 HTTP 读写。"""

    def __init__(self, client_getter=get_remote):
        self._client_getter = client_getter

    def _c(self):
        c = self._client_getter()
        if c is None:
            raise RemoteError("没有连接团队服务")
        return c

    def _item(self, d: dict) -> Note:
        return Note.from_dict({**d, "scope": PUBLIC})

    def _or_none(self, fn):
        try:
            return fn()
        except RemoteError as e:
            if e.status == 404:
                return None
            raise

    def list_notes(self, tag: str | None = None) -> list[Note]:
        params = {"tag": tag} if tag else None
        return [self._item(d) for d in self._c().get("/api/notes", params=params).get("items", [])]

    def get_note(self, filename: str) -> Note | None:
        d = self._or_none(lambda: self._c().get(f"/api/notes/{filename}"))
        return self._item(d) if d else None

    def search_content(self, keyword: str) -> list[Note]:
        kw = keyword.lower()
        return [n for n in self.list_notes() if kw in n.title.lower() or kw in n.content.lower()]

    def semantic_search(self, keyword: str, top_k: int = 5) -> list[SearchResult]:
        items = self._c().get("/api/notes/search", params={"q": keyword, "top_k": top_k}).get("items", [])
        return [SearchResult(filename=d.get("filename", ""), title=d.get("title", ""), content=d.get("content", ""),
                             score=float(d.get("score", 0.0)), tags=d.get("tags", []), scope=PUBLIC) for d in items]

    def create_note(self, title: str, content: str = "", tags: list[str] | None = None) -> Note:
        body = {"title": title, "content": content, "tags": tags or [], "scope": PUBLIC}
        return self._item(self._c().post("/api/notes", body))

    def update_note(self, filename: str, content: str | None = None, tags: list[str] | None = None) -> Note | None:
        d = self._or_none(lambda: self._c().put(f"/api/notes/{filename}", {"content": content, "tags": tags}))
        return self._item(d) if d else None

    def delete_note(self, filename: str) -> bool:
        return self._or_none(lambda: self._c().delete(f"/api/notes/{filename}")) is not None

    def archive_note(self, filename: str) -> bool:
        return self._or_none(lambda: self._c().post(f"/api/notes/{filename}/archive")) is not None


class PublicNoteStore(PublicStoreBase):

    def _row(self, r: dict) -> Note:
        return Note(filename=r["note_key"], title=r["title"], content=r["content"], tags=load_list(r["tags"]),
                    date=date_str(r["note_date"]), path=f"public:{r['note_key']}", scope=PUBLIC)

    def list_notes(self, tag: str | None = None) -> list[Note]:
        db = self.db()
        rows = db.fetchall(f"SELECT * FROM {db.t('notes')} WHERE archived=0 ORDER BY created_at")
        notes = [self._row(r) for r in rows]
        return [n for n in notes if tag in n.tags] if tag else notes

    def get_note(self, filename: str) -> Note | None:
        db = self.db()
        r = db.fetchone(f"SELECT * FROM {db.t('notes')} WHERE note_key=%s AND archived=0", (filename,))
        return self._row(r) if r else None

    def search_content(self, keyword: str) -> list[Note]:
        db = self.db()
        like = f"%{keyword}%"
        rows = db.fetchall(f"SELECT * FROM {db.t('notes')} WHERE archived=0 AND (title LIKE %s OR content LIKE %s) "
                           f"ORDER BY created_at", (like, like))
        return [self._row(r) for r in rows]

    def create_note(self, title: str, content: str = "", tags: list[str] | None = None) -> Note:
        db = self.db()
        slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")[:120] or "note"
        key = f"{slug}-{uuid.uuid4().hex[:6]}.md"     # 带随机后缀：多人同名笔记不冲突
        ts = now()
        db.execute(f"INSERT INTO {db.t('notes')} (note_key, title, content, tags, note_date, archived, "
                   f"created_at, updated_at) VALUES (%s,%s,%s,%s,%s,0,%s,%s)",
                   (key, title, content, dump_list(tags), date.today(), ts, ts))
        logger.info(f"已创建公共笔记: {title} ({key})")
        return self.get_note(key)

    def update_note(self, filename: str, content: str | None = None, tags: list[str] | None = None) -> Note | None:
        db = self.db()
        sets, args = [], []
        if content is not None:
            sets.append("content=%s")
            args.append(content)
        if tags is not None:
            sets.append("tags=%s")
            args.append(dump_list(tags))
        if sets:
            sets.append("updated_at=%s")
            args += [now(), filename]
            db.execute(f"UPDATE {db.t('notes')} SET {', '.join(sets)} WHERE note_key=%s AND archived=0", args)
        return self.get_note(filename)

    def delete_note(self, filename: str) -> bool:
        db = self.db()
        return db.execute(f"DELETE FROM {db.t('notes')} WHERE note_key=%s", (filename,)) > 0

    def archive_note(self, filename: str) -> bool:
        db = self.db()
        return db.execute(f"UPDATE {db.t('notes')} SET archived=1, updated_at=%s WHERE note_key=%s AND archived=0",
                          (now(), filename)) > 0


class ScopedNoteStore(MergedReadMixin):
    def __init__(self, private: NoteStore, public: PublicNoteStore | None):
        self._private = private
        self._public = public

    def list_notes(self, tag: str | None = None) -> list[Note]:
        return self._private.list_notes(tag=tag) + self._public_read(lambda: self._public.list_notes(tag=tag), [])

    def get_note(self, filename: str) -> Note | None:
        return self._private.get_note(filename) or self._public_read(lambda: self._public.get_note(filename), None)

    def search_content(self, keyword: str) -> list[Note]:
        return self._private.search_content(keyword) + \
            self._public_read(lambda: self._public.search_content(keyword), [])

    def semantic_search_public(self, keyword: str, top_k: int = 5) -> list[SearchResult] | None:
        """personal：公共笔记的语义检索交给 team 服务。返回 None 表示公共一侧不走远程（team 自己查本机 Chroma）。"""
        if not hasattr(self._public, "semantic_search"):
            return None
        return self._public_read(lambda: self._public.semantic_search(keyword, top_k), [])

    def scope_of(self, filename: str) -> str | None:
        if self._private.get_note(filename):
            return PRIVATE
        if self._public is not None and self._public.get_note(filename):
            return PUBLIC
        return None

    def _owner(self, filename: str):
        scope = self.scope_of(filename)
        return {PRIVATE: self._private, PUBLIC: self._public}.get(scope)

    def create_note(self, title: str, content: str = "", tags: list[str] | None = None,
                    scope: str = PRIVATE) -> Note:
        if scope == PUBLIC:
            if self._public is None:
                raise RuntimeError("公共库未启用，不能创建公共笔记")
            return self._public.create_note(title, content, tags)
        note = self._private.create_note(title, content, tags)
        note.scope = PRIVATE
        return note

    def update_note(self, filename: str, content: str | None = None, tags: list[str] | None = None) -> Note | None:
        owner = self._owner(filename)
        return owner.update_note(filename, content, tags) if owner else None

    def delete_note(self, filename: str) -> bool:
        owner = self._owner(filename)
        return owner.delete_note(filename) if owner else False

    def archive_note(self, filename: str) -> bool:
        owner = self._owner(filename)
        return owner.archive_note(filename) if owner else False
