from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "NoteTool":
    """Factory for auto-discovery. Creates a NoteTool with default config."""
    from src.core.config import config
    notes_dir = config.resolve_path(config.get("storage.notes_dir", "data/notes"))
    return NoteTool(
        notes_dir=str(notes_dir),
        archive_dir=str(notes_dir / "archive"),
        persist_dir=str(config.resolve_path(config.get("storage.vector_db_dir", "data/chroma"))),
        collection_name="notes",
    )


class NoteInput(BaseModel):
    action: Literal["list", "read", "create", "archive"] = Field(
        description="操作类型：list=列出, read=读取, create=创建, archive=归档"
    )
    filename: Optional[str] = Field(default=None, description="read 或 archive 时的文件名")
    title: Optional[str] = Field(default=None, description="create 时的笔记标题")
    content: Optional[str] = Field(default=None, description="create 时的笔记正文")
    tags: Optional[list[str]] = Field(default=None, description="create 时的标签")


class NoteTool(BaseTool):
    name: str = "notes"
    description: str = "管理笔记：列出、读取、创建、归档。如需语义搜索笔记内容请用 rag_search 工具。"
    args_schema: type[BaseModel] = NoteInput
    notes_dir: str = ""
    archive_dir: str = ""
    persist_dir: str = ""
    collection_name: str = "notes"

    def _run(self, action: str, filename: str | None = None, title: str | None = None,
             content: str | None = None, tags: list[str] | None = None) -> str:
        from src.domains.notes import get_notes_domain

        domain = get_notes_domain()
        if not domain:
            return "笔记服务未就绪，请稍后重试。"

        if action == "list":
            notes = domain.list_notes()
            if not notes:
                return "没有笔记。"
            return "\n".join(
                f"- {n.title or n.filename} ({n.filename})"
                for n in notes
            )

        elif action == "read":
            if not filename:
                return "请提供要读取的文件名。"
            note = domain.get_note(filename)
            if not note:
                return f"笔记不存在：{filename}"
            return note.content

        elif action == "create":
            if not title:
                return "创建笔记需要提供标题。"
            note = domain.create_note(title=title, content=content or "", tags=tags)
            return f"已记录笔记：{title} ({note.filename})"

        elif action == "archive":
            if not filename:
                return "请提供要归档的文件名。"
            if domain.archive_note(filename):
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
