import uuid
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path


class TodoInput(BaseModel):
    action: Literal["list", "search", "create", "done", "delete"] = Field(
        description="操作类型：list=列出, search=搜索, create=创建, done=标记完成, delete=删除"
    )
    status: Optional[Literal["active", "all", "pending", "done"]] = Field(
        default=None, description="list 时使用：active=进行中的, all=全部, pending=待完成, done=已完成。默认 active"
    )
    keyword: Optional[str] = Field(default=None, description="search 时的搜索关键词")
    title: Optional[str] = Field(default=None, description="create 时的待办标题")
    priority: Optional[Literal["high", "medium", "low"]] = Field(
        default=None, description="create 时的优先级：high=高, medium=中, low=低"
    )
    due: Optional[str] = Field(default=None, description="create 时的截止日期，格式 YYYY-MM-DD")
    todo_id: Optional[str] = Field(default=None, description="done 或 delete 时的待办 ID")


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = "管理待办事项：查看、搜索、创建、标记完成、删除。查看时默认显示进行中的项目。"
    args_schema: type[BaseModel] = TodoInput
    data_file: str = ""

    def _run(self, action: str, status: str | None = None, keyword: str | None = None,
             title: str | None = None, priority: str | None = None, due: str | None = None,
             todo_id: str | None = None) -> str:
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

        elif action == "done":
            if not todo_id:
                return "标记完成需要提供待办 ID。"
            for t in todos:
                if t["id"] == todo_id:
                    t["status"] = "done"
                    save_json(path, todos)
                    return f"已将「{t['title']}」标记为已完成。"
            return f"未找到待办 ID: {todo_id}"

        elif action == "delete":
            if not todo_id:
                return "删除需要提供待办 ID。"
            for i, t in enumerate(todos):
                if t["id"] == todo_id:
                    title = t["title"]
                    todos.pop(i)
                    save_json(path, todos)
                    return f"已删除待办：{title}"
            return f"未找到待办 ID: {todo_id}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
