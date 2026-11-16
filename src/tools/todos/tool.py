import json as _json
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from src.core.db import SCOPE_FIELD_DESC, scope_tag, public_unavailable_note


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
    scope: Optional[Literal["public", "private"]] = Field(default=None, description=SCOPE_FIELD_DESC)

    @field_validator("updates", mode="before")
    @classmethod
    def _parse_updates(cls, v):
        if isinstance(v, str):
            return _json.loads(v)
        return v


_STATUS_MAP = {"pending": "待完成", "in_progress": "进行中", "done": "已完成"}
_PRIORITY_MAP = {"high": "高", "medium": "中", "low": "低"}


def _format_todo(t) -> str:
    """格式化单条待办为文本。"""
    st = _STATUS_MAP.get(t.status, "未知")
    pr = _PRIORITY_MAP.get(t.priority, "-")
    return f"- [{t.id}] {scope_tag(t.scope)} [{st}] 优先级{pr} {t.title} (截止: {t.due or '无'})"


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

    def _resolve_todo_id(self, domain, todo_id: str | None,
                         title: str | None) -> str | None:
        """通过 todo_id 或 title 搜索解析待办 ID。"""
        if todo_id:
            return todo_id
        if title:
            matches = domain.search(title)
            if matches:
                return matches[0].id
        return None

    def _run(self, action: str, status: str | None = None, keyword: str | None = None,
             title: str | None = None, priority: str | None = None, due: str | None = None,
             todo_id: str | None = None, updates: dict | None = None, scope: str | None = None) -> str:
        from src.core.db import ScopeError, DatabaseError
        try:
            return self._dispatch(action, status, keyword, title, priority, due, todo_id, updates, scope)
        except (ScopeError, DatabaseError) as e:
            return f"操作失败：{e}"

    def _dispatch(self, action, status, keyword, title, priority, due, todo_id, updates, scope) -> str:
        from src.domains.todos import get_todo_domain

        domain = get_todo_domain()
        if not domain:
            return "待办服务未就绪，请稍后重试。"

        if action == "list":
            todos = domain.list_todos(status or "active")
            note = public_unavailable_note(domain.public_error)
            if not todos:
                return "没有待办事项。" + note
            return "\n".join(_format_todo(t) for t in todos) + note

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            matches = domain.search(keyword)
            note = public_unavailable_note(domain.public_error)
            if not matches:
                return f"没有找到包含「{keyword}」的待办。" + note
            return "\n".join(_format_todo(t) for t in matches) + note

        elif action == "create":
            if not title:
                return "创建待办需要提供标题。"
            t = domain.create_todo(title=title, priority=priority or "medium", due=due or "", scope=scope)
            pr = _PRIORITY_MAP.get(t.priority, "-")
            return f"已添加{scope_tag(t.scope)}待办（优先级{pr}）：{title}，截止 {due or '未设'}"

        elif action == "update":
            if not updates and not priority and not due:
                return "修改待办需要提供要修改的字段。"
            updates = updates or {}
            if priority and "priority" not in updates:
                updates["priority"] = priority
            if due and "due" not in updates:
                updates["due"] = due

            resolved_id = self._resolve_todo_id(domain, todo_id, title)
            if not resolved_id:
                return f"未找到待办：{todo_id or title}"

            result = domain.update_todo(resolved_id, updates)
            if result:
                return f"已更新待办：{result.title}"
            return f"未找到待办：{resolved_id}"

        elif action == "done":
            resolved_id = self._resolve_todo_id(domain, todo_id, title)
            if not resolved_id:
                return f"未找到待办：{todo_id or title}"

            result = domain.mark_done(resolved_id)
            if result:
                return f"已将「{result.title}」标记为已完成。"
            return f"未找到待办：{resolved_id}"

        elif action == "delete":
            resolved_id = self._resolve_todo_id(domain, todo_id, title)
            if not resolved_id:
                return f"未找到待办：{todo_id or title}"

            if domain.delete_todo(resolved_id):
                return f"已删除待办：{resolved_id}"
            return f"未找到待办：{resolved_id}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
