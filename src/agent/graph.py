"""Polaris Agent Graph — confirm/cancel → agent ⇄ tools."""

import threading
from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.executor import agent_node, tool_node, should_continue
from src.core.tools.registry import ToolRegistry


CONFIRM_WORDS = {"确认", "确定", "确认删除", "是", "是的", "好", "好的", "可以", "删吧", "删除吧", "yes", "y", "ok"}
CANCEL_WORDS = {"取消", "不", "不要", "不用", "算了", "no", "n", "cancel"}


def _run_action(action: dict) -> str:
    registry = ToolRegistry.get_instance()
    tool = registry.get(action["target_tool"])
    from src.core.errors import NotFoundError, format_tool_error
    if not tool:
        return format_tool_error(NotFoundError(f"未找到工具：{action['target_tool']}"))
    try:
        result = tool.invoke(action["params"])
        return str(result) if not isinstance(result, str) else result
    except Exception as e:
        return format_tool_error(e)


def confirm_node(state: AgentState) -> dict:
    """Pre-processing: handle pending action confirm/cancel."""
    pending = state.get("pending_action")
    if not pending:
        return {}

    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else ""
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = " ".join(text_parts)
    stripped = content.strip().rstrip("。.!！~～ ").lower() if isinstance(content, str) else ""

    if stripped in CONFIRM_WORDS:
        # 新格式 {"actions": [...]}：本轮的多个删除一起执行；兼容旧格式（单个操作）
        actions = pending.get("actions") or [pending]
        lines = []
        for a in actions:
            result = _run_action(a)
            desc = a.get("description")
            if desc and result.startswith("已删除"):
                result = f"已删除{desc}"
            elif desc:
                result = f"删除{desc}失败：{result}"
            lines.append(result)
        result_str = "\n".join(lines)
        return {"pending_action": None, "messages": [], "final_response": result_str}
    elif stripped in CANCEL_WORDS:
        return {"pending_action": None, "messages": [], "final_response": "已取消操作。"}
    else:
        return {"pending_action": None}


def should_end_after_confirm(state: AgentState) -> str:
    if state.get("final_response"):
        return "end"
    return "agent"


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("confirm", confirm_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.set_entry_point("confirm")

    builder.add_conditional_edges(
        "confirm",
        should_end_after_confirm,
        {"agent": "agent", "end": END},
    )

    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


_compiled_agent = None
_agent_lock = threading.Lock()


def get_agent():
    global _compiled_agent
    if _compiled_agent is None:
        with _agent_lock:
            if _compiled_agent is None:
                _compiled_agent = build_agent_graph()
    return _compiled_agent
