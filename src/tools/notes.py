import threading
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path


def create_default() -> "NoteTool":
    """Factory for auto-discovery. Creates a NoteTool with default config."""
    from src.config import NOTES_DIR, ARCHIVE_DIR, CHROMA_PERSIST_DIR
    return NoteTool(
        notes_dir=str(NOTES_DIR),
        archive_dir=str(ARCHIVE_DIR),
        persist_dir=str(CHROMA_PERSIST_DIR),
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
            # Auto-index in background, don't block the response
            if self.persist_dir:
                threading.Thread(
                    target=_index_note,
                    args=(filepath.name, title, content or "", tags or [],
                          self.persist_dir, self.collection_name),
                    daemon=True,
                ).start()
            return f"已记录笔记：{title} ({filepath.name})"

        elif action == "archive":
            if not filename:
                return "请提供要归档的文件名。"
            filepath = notes_path / filename
            if archive_note(filepath, archive_path):
                # Remove from vector index in background
                if self.persist_dir:
                    threading.Thread(
                        target=_deindex_note,
                        args=(filename, self.persist_dir, self.collection_name),
                        daemon=True,
                    ).start()
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)


def _index_note(filename: str, title: str, content: str, tags: list[str],
                persist_dir: str, collection_name: str) -> None:
    """Background indexing."""
    import logging
    logger = logging.getLogger("polaris.tools.notes")
    try:
        from src.data_layer.vector_store import add_note_to_index
        add_note_to_index(filename, title, content, tags, persist_dir, collection_name)
        logger.debug(f"笔记已索引: {filename}")
    except Exception as e:
        logger.warning(f"笔记索引失败 ({filename}): {e}")


def _deindex_note(filename: str, persist_dir: str, collection_name: str) -> None:
    """Background de-indexing."""
    import logging
    logger = logging.getLogger("polaris.tools.notes")
    try:
        from src.data_layer.vector_store import remove_note_from_index
        remove_note_from_index(filename, persist_dir, collection_name)
        logger.debug(f"笔记已从索引移除: {filename}")
    except Exception as e:
        logger.warning(f"笔记移除索引失败 ({filename}): {e}")
