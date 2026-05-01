"""Polaris Agent Graph — command interception → agent ⇄ tools."""

from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.executor import agent_node, tool_node, should_continue
from src.session.commands import handle_command
from src.session.manager import get_session_manager


def command_node(state: AgentState) -> dict:
    """Pre-processing: intercept /commands, pass everything else through."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else ""

    if not content.strip().startswith("/"):
        return {}

    session_mgr = get_session_manager()
    response = handle_command(content.strip(), session_mgr)
    if response:
        if content.strip() == "/reset":
            session_mgr.reset_active()
        return {"messages": [], "final_response": response}

    return {}


def should_end_after_command(state: AgentState) -> str:
    if state.get("final_response"):
        return "end"
    return "agent"


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("command", command_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.set_entry_point("command")

    builder.add_conditional_edges(
        "command",
        should_end_after_command,
        {"agent": "agent", "end": END},
    )

    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


def get_agent():
    return build_agent_graph()
