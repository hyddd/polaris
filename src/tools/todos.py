import uuid
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path


class TodoInput(BaseModel):
    action: Literal["list", "search", "create", "update", "done", "delete"] = Field(
        description="操作类型：list=列出, search=搜索, create=创建, update=修改, done=标记完成, delete=删除"
    )
    status: Optional[Literal["active", "all", "pending", "done"]] = Field(
        default=None, description="list 时使用：active=进行中的, all=全部, pending=待完成, done=已完成。默认 active"
    )
    keyword: Optional[str] = Field(default=None, description="search 时的搜索关键词")
    title: Optional[str] = Field(default=None, description="create/update/done/delete 时的待办标题（用于匹配）")
    priority: Optional[Literal["high", "medium", "low"]] = Field(
        default=None, description="create/update 时的优先级：high=高, medium=中, low=低"
    )
    due: Optional[str] = Field(default=None, description="create/update 时的截止日期，格式 YYYY-MM-DD")
    todo_id: Optional[str] = Field(default=None, description="update/done/delete 时的待办 ID（优先级高于 title）")
    updates: Optional[dict] = Field(default=None, description="update 时要修改的字段，如 {\"title\":\"新标题\", \"due\":\"2026-05-03\"}")


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = """管理待办事项。修改/完成/删除时，必须先用 search 搜索获取 todo_id，再用 todo_id 操作。
示例流程：用户说"把晨会标为完成" → 先 search(keyword="晨会") 获取 todo_id → 再 done(todo_id="xxx")"""
    args_schema: type[BaseModel] = TodoInput
    data_file: str = ""

    def _run(self, action: str, status: str | None = None, keyword: str | None = None,
             title: str | None = None, priority: str | None = None, due: str | None = None,
             todo_id: str | None = None, updates: dict | None = None) -> str:
        from src.data_layer.loader import load_todos, save_json

        path = Path(self.data_file)
        todos = load_todos(path)
        status_map = {"pending": "待完成", "in_progress": "进行中", "done": "已完成"}
        priority_map = {"high": "高", "medium": "中", "low": "低"}

        if action == "list":
            status_filter = status or "active"
            if status_filter == "active":
                filtered = [t for t in todos if t.get("status") in ("pending", "in_progress")]
            elif status_filter == "all":
                filtered = list(todos)
            else:
                filtered = [t for t in todos if t.get("status") == status_filter]

            if not filtered:
                return "没有待办事项。"
            lines = []
            for t in filtered:
                st = status_map.get(t.get("status", ""), "未知")
                pr = priority_map.get(t.get("priority", ""), "-")
                lines.append(f"- [{st}] 优先级{pr} {t['title']} (截止: {t.get('due', '无')})")
            return "\n".join(lines)

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            matches = [t for t in todos if keyword.lower() in t.get("title", "").lower()
                       or keyword.lower() in " ".join(t.get("tags", [])).lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的待办。"
            lines = []
            for t in matches:
                st = status_map.get(t.get("status", ""), "未知")
                pr = priority_map.get(t.get("priority", ""), "-")
                lines.append(f"- [{st}] 优先级{pr} {t['title']} (截止: {t.get('due', '无')})")
            return "\n".join(lines)

        elif action == "create":
            if not title:
                return "创建待办需要提供标题。"
            new_todo = {
                "id": f"todo-{uuid.uuid4().hex[:8]}",
                "title": title,
                "priority": priority or "medium",
                "status": "pending",
                "due": due or "",
                "tags": [],
            }
            todos.append(new_todo)
            save_json(path, todos)
            pr = priority_map.get(new_todo["priority"], "-")
            return f"已添加待办（优先级{pr}）：{title}，截止 {due or '未设'}"

        elif action == "update":
            if not updates and not title and not priority and not due:
                return "修改待办需要提供要修改的字段。"
            updates = updates or {}
            if title and "title" not in updates:
                updates["title"] = title
            if priority and "priority" not in updates:
                updates["priority"] = priority
            if due and "due" not in updates:
                updates["due"] = due
            # Find by todo_id or title
            for t in todos:
                matched = False
                if todo_id and t["id"] == todo_id:
                    matched = True
                elif title and not todo_id and title.lower() in t.get("title", "").lower():
                    matched = True
                if matched:
                    t.update(updates)
                    save_json(path, todos)
                    return f"已更新待办：{t.get('title', todo_id)}"
            return f"未找到待办：{todo_id or title}"

        elif action == "done":
            # Find by todo_id or title
            for t in todos:
                matched = False
                if todo_id and t["id"] == todo_id:
                    matched = True
                elif title and not todo_id and title.lower() in t.get("title", "").lower():
                    matched = True
                if matched:
                    t["status"] = "done"
                    save_json(path, todos)
                    return f"已将「{t['title']}」标记为已完成。"
            return f"未找到待办：{todo_id or title}"

        elif action == "delete":
            # Find by todo_id or title
            for i, t in enumerate(todos):
                matched = False
                if todo_id and t["id"] == todo_id:
                    matched = True
                elif title and not todo_id and title.lower() in t.get("title", "").lower():
                    matched = True
                if matched:
                    title = t["title"]
                    todos.pop(i)
                    save_json(path, todos)
                    return f"已删除待办：{title}"
            return f"未找到待办：{todo_id or title}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
