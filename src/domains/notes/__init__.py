"""NotesDomain — 笔记管理基础设施。"""

from .domain import get_notes_domain, set_notes_domain, NotesDomain
from .models import Note, SearchResult

__all__ = ["get_notes_domain", "set_notes_domain", "NotesDomain", "Note", "SearchResult"]
