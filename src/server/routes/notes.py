"""Admin API: Notes management."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain, scope_errors

router = APIRouter()


def _require_notes_domain():
    from src.domains.notes import get_notes_domain
    return require_domain(get_notes_domain, "笔记")


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    tags: list[str] = []
    scope: str | None = None   # public / private；不传用默认


class NoteUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None


@router.get("/api/notes")
def list_notes(tag: str = None):
    domain = _require_notes_domain()
    notes = domain.list_notes(tag=tag)
    return {"items": [n.to_dict() for n in notes], "public_error": domain.public_error}


@router.get("/api/notes/search")
def search_notes(q: str = "", top_k: int = 5):
    domain = _require_notes_domain()
    results = domain.search(q, top_k=top_k)
    return {"items": [r.to_dict() for r in results[:top_k]], "public_error": domain.public_error}


@router.get("/api/notes/{filename}")
def get_note(filename: str):
    domain = _require_notes_domain()
    with scope_errors():
        note = domain.get_note(filename)
    if not note:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return note.to_dict()


@router.post("/api/notes")
def create_note(req: NoteCreate):
    domain = _require_notes_domain()
    with scope_errors():
        note = domain.create_note(req.title, req.content, req.tags, scope=req.scope)
    return note.to_dict()


@router.put("/api/notes/{filename}")
def update_note(filename: str, req: NoteUpdate):
    domain = _require_notes_domain()
    with scope_errors():
        note = domain.update_note(filename, content=req.content, tags=req.tags)
    if not note:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return note.to_dict()


@router.delete("/api/notes/{filename}")
def delete_note(filename: str):
    domain = _require_notes_domain()
    with scope_errors():
        deleted = domain.delete_note(filename)
    if not deleted:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return {"ok": True}


@router.post("/api/notes/{filename}/archive")
def archive_note(filename: str):
    domain = _require_notes_domain()
    with scope_errors():
        archived = domain.archive_note(filename)
    if not archived:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return {"ok": True}
