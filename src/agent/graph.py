"""Polaris Agent Graph — command interception → agent ⇄ tools."""

from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.executor import agent_node, tool_node, should_continue, _get_compressor
from src.system_commands import handle_command


def command_node(state: AgentState) -> dict:
    """Pre-processing: intercept /commands, pass everything else through."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else ""

    if not content.strip().startswith("/"):
        return {}

    compressor = _get_compressor()
    response = _handle_command_in_graph(content.strip(), messages, compressor)
    if response:
        if content.strip() == "/reset":
            return {"messages": [], "final_response": response}
        return {"final_response": response}

    return {}


def _handle_command_in_graph(text: str, messages: list, compressor) -> str | None:
    class _MsgStore:
        def __init__(self, msgs):
            self._messages = list(msgs)

        def get_history(self):
            return self._messages

    store = _MsgStore(messages)
    try:
        return handle_command(text, store, compressor)
    except Exception:
        return None


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

    # Command → Agent or END
    builder.add_conditional_edges(
        "command",
        should_end_after_command,
        {"agent": "agent", "end": END},
    )

    # ReAct loop: Agent ⇄ Tools
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


def get_agent():
    return build_agent_graph()
