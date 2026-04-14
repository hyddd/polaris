from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path


class NoteInput(BaseModel):
    action: Literal["list", "read", "create", "search", "archive"] = Field(
        description="操作类型：list=列出, read=读取, create=创建, search=搜索, archive=归档"
    )
    filename: Optional[str] = Field(default=None, description="read 或 archive 时的文件名")
    title: Optional[str] = Field(default=None, description="create 时的笔记标题")
    content: Optional[str] = Field(default=None, description="create 时的笔记正文")
    tags: Optional[list[str]] = Field(default=None, description="create 时的标签")
    keyword: Optional[str] = Field(default=None, description="search 时的搜索关键词")


class NoteTool(BaseTool):
    name: str = "notes"
    description: str = "管理笔记：列出、读取、创建、搜索（关键词）、归档。"
    args_schema: type[BaseModel] = NoteInput
    notes_dir: str = ""
    archive_dir: str = ""

    def _run(self, action: str, filename: str | None = None, title: str | None = None,
             content: str | None = None, tags: list[str] | None = None,
             keyword: str | None = None) -> str:
        from src.data_layer.loader import load_notes, save_note, archive_note

        notes_path = Path(self.notes_dir)
        archive_path = Path(self.archive_dir)

        if action == "list":
            notes = load_notes(notes_path)
            if not notes:
                return "没有笔记。"
            return "\n".join(
                f"- {n['metadata'].get('title', n['filename'])} ({n['filename']})"
                for n in notes
            )

        elif action == "read":
            if not filename:
                return "请提供要读取的文件名。"
            filepath = notes_path / filename
            if not filepath.exists():
                return f"笔记不存在：{filename}"
            return filepath.read_text(encoding="utf-8")

        elif action == "create":
            if not title:
                return "创建笔记需要提供标题。"
            filepath = save_note(notes_path, title, content or "", tags)
            return f"已记录笔记：{title} ({filepath.name})"

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            notes = load_notes(notes_path)
            matches = [n for n in notes
                       if keyword.lower() in n["content"].lower()
                       or keyword.lower() in n["metadata"].get("title", "").lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的笔记。"
            return "\n\n".join(
                f"## {n['metadata'].get('title', n['filename'])}\n{n['content'][:300]}"
                for n in matches
            )

        elif action == "archive":
            if not filename:
                return "请提供要归档的文件名。"
            filepath = notes_path / filename
            if archive_note(filepath, archive_path):
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
