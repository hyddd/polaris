"""Polaris Agent Graph — confirm/cancel → agent ⇄ tools."""

import threading
from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.executor import agent_node, tool_node, should_continue
from src.core.tools.registry import ToolRegistry


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
    stripped = content.strip() if isinstance(content, str) else ""

    if stripped in ("确认", "yes", "ok", "确定"):
        registry = ToolRegistry.get_instance()
        tool = registry.get(pending["target_tool"])
        if tool:
            try:
                result = tool.invoke(pending["params"])
                result_str = str(result) if not isinstance(result, str) else result
            except Exception as e:
                from src.core.errors import format_tool_error
                result_str = format_tool_error(e)
        else:
            from src.core.errors import NotFoundError, format_tool_error
            result_str = format_tool_error(NotFoundError(f"未找到工具：{pending['target_tool']}"))
        return {"pending_action": None, "messages": [], "final_response": result_str}
    elif stripped in ("取消", "cancel", "no"):
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
