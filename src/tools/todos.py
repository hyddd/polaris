import json
import uuid
from langchain_core.tools import BaseTool
from pathlib import Path


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = (
        "Manage todo items. Commands: "
        "list active (pending+in_progress, default), list all, list pending, list done, "
        "search <keyword>, create {\"title\":...,\"priority\":...,\"due\":...}, done <id>, delete <id>"
    )
    data_file: str = ""

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_todos, save_json

        path = Path(self.data_file)
        todos = load_todos(path)
        cmd = command.strip().lower()

        if cmd.startswith("list"):
            status_filter = cmd.replace("list", "").strip()
            if status_filter == "active":
                todos = [t for t in todos if t.get("status") in ("pending", "in_progress")]
            elif status_filter and status_filter != "all":
                todos = [t for t in todos if t.get("status") == status_filter]
            if not todos:
                return "没有待办事项。"
            lines = []
            for t in todos:
                status_text = {"pending": "待完成", "in_progress": "进行中", "done": "已完成"}.get(t.get("status", ""), "未知")
                priority_text = {"high": "高", "medium": "中", "low": "低"}.get(t.get("priority", ""), "-")
                lines.append(
                    f"- [{status_text}] 优先级{priority_text} {t['title']} "
                    f"(截止: {t.get('due', '无')})"
                )
            return "\n".join(lines)

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            matches = [
                t for t in todos
                if keyword.lower() in t.get("title", "").lower()
                or keyword.lower() in " ".join(t.get("tags", [])).lower()
            ]
            if not matches:
                return f"没有找到包含「{keyword}」的待办。"
            lines = []
            for t in matches:
                status_text = {"pending": "待完成", "in_progress": "进行中", "done": "已完成"}.get(t.get("status", ""), "未知")
                priority_text = {"high": "高", "medium": "中", "low": "低"}.get(t.get("priority", ""), "-")
                lines.append(f"- [{status_text}] 优先级{priority_text} {t['title']} (截止: {t.get('due', '无')})")
            return "\n".join(lines)

        elif cmd.startswith("create"):
            try:
                new_todo = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建待办需要 JSON：create {\"title\": \"...\", \"priority\": \"high|medium|low\", \"due\": \"YYYY-MM-DD\"}"
            new_todo["id"] = f"todo-{uuid.uuid4().hex[:8]}"
            new_todo.setdefault("status", "pending")
            new_todo.setdefault("tags", [])
            todos.append(new_todo)
            save_json(path, todos)
            priority_text = {"high": "高", "medium": "中", "low": "低"}.get(new_todo.get("priority", ""), "-")
            return f"已添加待办（优先级{priority_text}）：{new_todo['title']}，截止 {new_todo.get('due', '未设')}"

        elif cmd.startswith("done"):
            todo_id = cmd.replace("done", "").strip()
            for t in todos:
                if t["id"] == todo_id:
                    t["status"] = "done"
                    save_json(path, todos)
                    return f"已将「{t['title']}」标记为已完成。"
            return f"未找到待办 ID: {todo_id}"

        elif cmd.startswith("delete"):
            todo_id = cmd.replace("delete", "").strip()
            for i, t in enumerate(todos):
                if t["id"] == todo_id:
                    title = t["title"]
                    todos.pop(i)
                    save_json(path, todos)
                    return f"已删除待办：{title}"
            return f"未找到待办 ID: {todo_id}"

        return "可用命令：list [status], search <keyword>, create <json>, done <id>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
