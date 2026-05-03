import uuid
import json as _json
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from src.storage import JsonFileStore
from src.tools._utils import find_by_id_or_title


def create_default() -> "TodoTool":
    """Factory for auto-discovery. Creates a TodoTool with default config."""
    from src.core.config import config
    return TodoTool(
        data_file=str(config.resolve_path(config.get("storage.todos_file", "data/todos.json")))
    )


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
    updates: Optional[dict | str] = Field(default=None, description="update 时要修改的字段")

    @field_validator("updates", mode="before")
    @classmethod
    def _parse_updates(cls, v):
        if isinstance(v, str):
            return _json.loads(v)
        return v


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = """管理待办事项。

规则：
1. 修改待办必须用 update，禁止 delete + create
2. 完成/删除/修改前必须先 search 获取 todo_id
3. 用户说"改一下""推迟""换个优先级"等，都是修改意图，用 update

示例流程：
- "把晨会标为完成" → search(keyword="晨会") → done(todo_id="xxx")
- "把明天的截止日期改到后天" → search(keyword="xxx") → update(todo_id="xxx", due="后天日期")"""
    args_schema: type[BaseModel] = TodoInput
    data_file: str = ""
    _store: JsonFileStore | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._store = JsonFileStore(self.data_file)

    def _run(self, action: str, status: str | None = None, keyword: str | None = None,
             title: str | None = None, priority: str | None = None, due: str | None = None,
             todo_id: str | None = None, updates: dict | None = None) -> str:
        todos = self._store.load()
        if not isinstance(todos, list):
            todos = []
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
                lines.append(f"- [{t['id']}] [{st}] 优先级{pr} {t['title']} (截止: {t.get('due', '无')})")
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
                lines.append(f"- [{t['id']}] [{st}] 优先级{pr} {t['title']} (截止: {t.get('due', '无')})")
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
            self._store.save(todos)
            pr = priority_map.get(new_todo["priority"], "-")
            return f"已添加待办（优先级{pr}）：{title}，截止 {due or '未设'}"

        elif action == "update":
            if not updates and not priority and not due:
                return "修改待办需要提供要修改的字段。"
            updates = updates or {}
            # title param is for matching only, new title must go through updates["title"]
            if priority and "priority" not in updates:
                updates["priority"] = priority
            if due and "due" not in updates:
                updates["due"] = due
            # Find by todo_id or title
            t = find_by_id_or_title(todos, "id", todo_id, "title", title)
            if t:
                t.update(updates)
                self._store.save(todos)
                return f"已更新待办：{t.get('title', todo_id)}"
            return f"未找到待办：{todo_id or title}"

        elif action == "done":
            # Find by todo_id or title
            t = find_by_id_or_title(todos, "id", todo_id, "title", title)
            if t:
                t["status"] = "done"
                self._store.save(todos)
                return f"已将「{t['title']}」标记为已完成。"
            return f"未找到待办：{todo_id or title}"

        elif action == "delete":
            # Find by todo_id or title
            t = find_by_id_or_title(todos, "id", todo_id, "title", title)
            if t:
                matched_title = t["title"]
                todos.remove(t)
                self._store.save(todos)
                return f"已删除待办：{matched_title}"
            return f"未找到待办：{todo_id or title}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
