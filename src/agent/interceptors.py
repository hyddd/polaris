"""Action interceptors — intercept tool calls before execution for confirmation.

Each interceptor is registered for a specific tool and action.
The tool_node runs all matching interceptors before executing a tool.
"""

from dataclasses import dataclass, field
from typing import Protocol, Optional


@dataclass
class InterceptResult:
    pending_action: dict
    tool_message_content: str


class ActionInterceptor(Protocol):
    """Protocol for action interceptors."""

    def should_intercept(self, tool_name: str, tool_args: dict) -> bool:
        """Return True if this interceptor should handle the tool call."""
        ...

    def intercept(self, tool_name: str, tool_args: dict, call_id: str) -> InterceptResult:
        """Build the pending action and tool message content."""
        ...


@dataclass
class DeleteInterceptor:
    """Intercept delete operations for confirmation.

    Configurable per tool: maps tool name -> (action_value, id_field_names).
    """

    _rules: dict[str, tuple[str, list[str]]] = field(default_factory=lambda: {
        "calendar": ("delete", ["event_id"]),
        "todo": ("delete", ["todo_id"]),
        "notes": ("delete", ["filename"]),
    })

    def register(self, tool_name: str, action_value: str, id_fields: list[str]) -> None:
        self._rules[tool_name] = (action_value, id_fields)

    def should_intercept(self, tool_name: str, tool_args: dict) -> bool:
        rule = self._rules.get(tool_name)
        if not rule:
            return False
        action_value, _ = rule
        return tool_args.get("action") == action_value

    def intercept(self, tool_name: str, tool_args: dict, call_id: str) -> InterceptResult:
        _, id_fields = self._rules.get(tool_name, ("delete", []))
        target_id = ""
        for field_name in id_fields:
            target_id = tool_args.get(field_name, "")
            if target_id:
                break

        return InterceptResult(
            pending_action={
                "action_type": "delete",
                "target_tool": tool_name,
                "target_id": target_id,
                "description": f"删除 {tool_name} {target_id}",
                "params": tool_args,
                "tool_call_id": call_id,
            },
            tool_message_content=f"操作需要确认：删除 {tool_name}「{target_id}」。回复「确认」执行，「取消」放弃。",
        )


_interceptors: list[ActionInterceptor] = []


def register_interceptor(interceptor: ActionInterceptor) -> None:
    _interceptors.append(interceptor)


def get_interceptors() -> list[ActionInterceptor]:
    return list(_interceptors)


def init_default_interceptors() -> None:
    """Register the default set of interceptors."""
    if not _interceptors:
        register_interceptor(DeleteInterceptor())
