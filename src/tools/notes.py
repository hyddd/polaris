import json
from langchain_core.tools import BaseTool
from pathlib import Path


class NoteTool(BaseTool):
    name: str = "notes"
    description: str = (
        "Manage notes. Commands: list, read <filename>, "
        "create {\"title\":...,\"content\":...,\"tags\":[...]}, search <keyword>, archive <filename>"
    )
    notes_dir: str = ""
    archive_dir: str = ""

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_notes, save_note, archive_note

        notes_path = Path(self.notes_dir)
        archive_path = Path(self.archive_dir)
        cmd = command.strip().lower()

        if cmd == "list":
            notes = load_notes(notes_path)
            if not notes:
                return "没有笔记。"
            return "\n".join(
                f"- {n['metadata'].get('title', n['filename'])} ({n['filename']})"
                for n in notes
            )

        elif cmd.startswith("read"):
            filename = command.split("read", 1)[1].strip()
            filepath = notes_path / filename
            if not filepath.exists():
                return f"笔记不存在：{filename}"
            return filepath.read_text(encoding="utf-8")

        elif cmd.startswith("create"):
            try:
                data = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建笔记需要 JSON：create {\"title\":\"...\", \"content\":\"...\", \"tags\":[...]}"
            filepath = save_note(notes_path, data["title"], data.get("content", ""), data.get("tags"))
            return f"已记录笔记：{data['title']} ({filepath.name})"

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            notes = load_notes(notes_path)
            matches = [
                n for n in notes
                if keyword.lower() in n["content"].lower()
                or keyword.lower() in n["metadata"].get("title", "").lower()
            ]
            if not matches:
                return f"没有找到包含「{keyword}」的笔记。"
            return "\n\n".join(
                f"## {n['metadata'].get('title', n['filename'])}\n{n['content'][:300]}"
                for n in matches
            )

        elif cmd.startswith("archive"):
            filename = command.replace("archive", "").strip()
            filepath = notes_path / filename
            if archive_note(filepath, archive_path):
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        return "可用命令：list, read <filename>, create <json>, search <keyword>, archive <filename>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
