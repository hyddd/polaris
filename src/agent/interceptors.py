"""Action interceptors — intercept tool calls before execution for confirmation.

删除日程、待办、提醒前，由这里拦下、请用户确认一次；用户回复"确认"后由 graph.confirm_node 直接执行，
不再经过模型（系统提示词要求模型不要自己先问，避免确认两次）。
同一轮里的多个删除合并成一次确认、一起执行。
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class InterceptResult:
    action: dict                  # 一个待确认的操作：target_tool / params / tool_call_id / description
    tool_message_content: str


class ActionInterceptor(Protocol):
    """Protocol for action interceptors."""

    def should_intercept(self, tool_name: str, tool_args: dict) -> bool:
        """Return True if this interceptor should handle the tool call."""
        ...

    def intercept(self, tool_name: str, tool_args: dict, call_id: str) -> InterceptResult:
        """Build the pending action and tool message content."""
        ...


def _describe_calendar(args: dict) -> str:
    from src.core.db import scope_tag
    from src.domains.calendar import get_calendar_domain
    domain = get_calendar_domain()
    event = domain.get_event(args["event_id"]) if domain and args.get("event_id") else None
    if event:
        return f"日程 {scope_tag(event.scope)} {event.date} {event.time} {event.title}"
    return f"日程 {args.get('date') or ''} {args.get('title') or args.get('event_id') or ''}".strip()


def _describe_todo(args: dict) -> str:
    from src.core.db import scope_tag
    from src.domains.todos import get_todo_domain
    domain = get_todo_domain()
    todo = domain.get_todo(args["todo_id"]) if domain and args.get("todo_id") else None
    if todo:
        return f"待办 {scope_tag(todo.scope)} {todo.title}"
    return f"待办 {args.get('title') or args.get('todo_id') or ''}".strip()


def _describe_reminder(args: dict) -> str:
    from src.core.db import scope_tag
    from src.domains.reminder import get_reminder_domain
    domain = get_reminder_domain()
    reminder = domain.get(args["reminder_id"]) if domain and args.get("reminder_id") else None
    if reminder:
        return f"提醒 {scope_tag(reminder.scope)} {reminder.trigger_time:%Y-%m-%d %H:%M} {reminder.title}"
    return f"提醒 {args.get('reminder_id') or ''}".strip()


@dataclass
class DeleteInterceptor:
    """Intercept delete operations for confirmation. 规则：工具名 → (动作, 描述函数)。"""

    _rules: dict = field(default_factory=lambda: {
        "calendar": ("delete", _describe_calendar),
        "todo": ("delete", _describe_todo),
        "reminder": ("delete", _describe_reminder),
    })

    def register(self, tool_name: str, action_value: str, describe) -> None:
        self._rules[tool_name] = (action_value, describe)

    def should_intercept(self, tool_name: str, tool_args: dict) -> bool:
        rule = self._rules.get(tool_name)
        return bool(rule) and tool_args.get("action") == rule[0]

    def intercept(self, tool_name: str, tool_args: dict, call_id: str) -> InterceptResult:
        _, describe = self._rules[tool_name]
        try:
            description = describe(tool_args)
        except Exception:                 # 查不到详情时退回参数本身，不影响确认流程
            description = f"{tool_name} {tool_args}"
        return InterceptResult(
            action={"target_tool": tool_name, "params": tool_args, "tool_call_id": call_id,
                    "description": description},
            tool_message_content=(f"已暂停执行，等待用户确认：删除{description}。"
                                  f"请把待删除的内容列给用户，并提示回复「确认」执行、「取消」放弃；不要再次调用删除。"),
        )


def build_pending_action(actions: list[dict]) -> dict:
    """把本轮所有待确认的删除合并成一个待确认操作，用户确认一次全部执行。"""
    return {"action_type": "delete", "actions": actions,
            "description": "；".join(a["description"] for a in actions)}


_interceptors: list[ActionInterceptor] = []


def register_interceptor(interceptor: ActionInterceptor) -> None:
    _interceptors.append(interceptor)


def get_interceptors() -> list[ActionInterceptor]:
    return list(_interceptors)


def init_default_interceptors() -> None:
    """Register the default set of interceptors."""
    if not _interceptors:
        register_interceptor(DeleteInterceptor())
