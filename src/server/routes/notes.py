"""Admin API: Notes management."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain

router = APIRouter()


def _require_notes_domain():
    from src.domains.notes import get_notes_domain
    return require_domain(get_notes_domain, "笔记")


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    tags: list[str] = []


class NoteUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None


@router.get("/api/notes")
def list_notes(tag: str = None):
    domain = _require_notes_domain()
    notes = domain.list_notes(tag=tag)
    return {"items": [n.to_dict() for n in notes]}


@router.get("/api/notes/search")
def search_notes(q: str = "", top_k: int = 5):
    domain = _require_notes_domain()
    results = domain.search(q)
    return {"items": [r.to_dict() for r in results[:top_k]]}


@router.get("/api/notes/{filename}")
def get_note(filename: str):
    domain = _require_notes_domain()
    note = domain.get_note(filename)
    if not note:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return note.to_dict()


@router.post("/api/notes")
def create_note(req: NoteCreate):
    domain = _require_notes_domain()
    note = domain.create_note(req.title, req.content, req.tags)
    return note.to_dict()


@router.put("/api/notes/{filename}")
def update_note(filename: str, req: NoteUpdate):
    domain = _require_notes_domain()
    note = domain.update_note(filename, content=req.content, tags=req.tags)
    if not note:
        raise HTTPException(404, f"笔记不存在: {filename}")
    return note.to_dict()


@router.delete("/api/notes/{filename}")
def delete_note(filename: str):
    domain = _require_notes_domain()
    if not domain.delete_note(filename):
        raise HTTPException(404, f"笔记不存在: {filename}")
    return {"ok": True}
