"""NoteStore — 笔记文件系统持久化。"""

import logging
import re
import threading
from datetime import date
from pathlib import Path

from src.storage.loaders import format_note_file, parse_note_frontmatter
from .models import Note

logger = logging.getLogger("polaris.notes.store")


class NoteStore:
    """笔记文件系统存储，数据格式与现有 data/notes/ 兼容。"""

    def __init__(self, notes_dir: str, archive_dir: str):
        self._notes_dir = Path(notes_dir)
        self._archive_dir = Path(archive_dir)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _load_note_file(self, filepath: Path) -> Note | None:
        """从 .md 文件加载单条笔记。"""
        if not filepath.exists():
            return None
        content = filepath.read_text(encoding="utf-8")
        meta, body = parse_note_frontmatter(content)
        return Note(
            filename=filepath.name,
            title=meta.get("title", filepath.stem),
            content=body,
            tags=meta.get("tags", []),
            date=meta.get("date", ""),
            path=str(filepath),
        )

    def _list_note_files(self) -> list[Path]:
        """列出笔记目录下所有 .md 文件（不含 archive）。"""
        if not self._notes_dir.exists():
            return []
        return sorted(self._notes_dir.glob("*.md"))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_notes(self, tag: str | None = None) -> list[Note]:
        """列出所有笔记，可按标签筛选。"""
        notes = []
        for filepath in self._list_note_files():
            note = self._load_note_file(filepath)
            if note is None:
                continue
            if tag and tag not in note.tags:
                continue
            notes.append(note)
        return notes

    def get_note(self, filename: str) -> Note | None:
        """按文件名获取单条笔记。"""
        return self._load_note_file(self._notes_dir / filename)

    def search_content(self, keyword: str) -> list[Note]:
        """全关键词匹配搜索标题和正文。"""
        kw = keyword.lower()
        results = []
        for filepath in self._list_note_files():
            note = self._load_note_file(filepath)
            if note is None:
                continue
            if kw in note.title.lower() or kw in note.content.lower():
                results.append(note)
        return results

    # ------------------------------------------------------------------
    # 写操作（需要锁保护）
    # ------------------------------------------------------------------

    def create_note(self, title: str, content: str = "",
                    tags: list[str] | None = None) -> Note:
        """创建笔记并写入 .md 文件。"""
        with self._lock:
            self._notes_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
            filename = f"{slug}.md"
            filepath = self._notes_dir / filename
            metadata = {
                "title": title,
                "tags": tags or [],
                "date": date.today().isoformat(),
            }
            file_content = format_note_file(metadata, content)
            filepath.write_text(file_content, encoding="utf-8")
            logger.info(f"已创建笔记: {title} ({filename})")
            return Note(
                filename=filename,
                title=title,
                content=content,
                tags=tags or [],
                date=metadata["date"],
                path=str(filepath),
            )

    def update_note(self, filename: str, content: str | None = None,
                    tags: list[str] | None = None) -> Note | None:
        """更新笔记内容或标签。"""
        with self._lock:
            filepath = self._notes_dir / filename
            if not filepath.exists():
                return None
            raw = filepath.read_text(encoding="utf-8")
            meta, body = parse_note_frontmatter(raw)
            if content is not None:
                body = content
            if tags is not None:
                meta["tags"] = tags
            file_content = format_note_file(meta, body)
            filepath.write_text(file_content, encoding="utf-8")
            logger.info(f"已更新笔记: {filename}")
            return Note(
                filename=filename,
                title=meta.get("title", ""),
                content=body,
                tags=meta.get("tags", []),
                date=meta.get("date", ""),
                path=str(filepath),
            )

    def delete_note(self, filename: str) -> bool:
        """删除笔记文件。"""
        with self._lock:
            filepath = self._notes_dir / filename
            if not filepath.exists():
                return False
            filepath.unlink()
            logger.info(f"已删除笔记: {filename}")
            return True

    def archive_note(self, filename: str) -> bool:
        """归档笔记到 archive 目录。"""
        with self._lock:
            filepath = self._notes_dir / filename
            if not filepath.exists():
                return False
            self._archive_dir.mkdir(parents=True, exist_ok=True)
            filepath.rename(self._archive_dir / filename)
            logger.info(f"已归档笔记: {filename}")
            return True
