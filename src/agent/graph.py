from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.executor import agent_node, tool_node, should_continue, _get_compressor
from src.system_commands import handle_command


def command_node(state: AgentState) -> dict:
    """Pre-processing: intercept system commands, pass everything else through."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else ""

    if not content.strip().startswith("/"):
        return {}  # Not a command, pass through to router

    # System command — handle without LLM
    compressor = _get_compressor()
    # Create a temporary MemoryManager-like wrapper for the compressor
    response = _handle_command_in_graph(content.strip(), messages, compressor)
    if response:
        # /reset: also clear messages from state
        if content.strip() == "/reset":
            return {"messages": [], "final_response": response}
        return {"final_response": response}

    return {}


def _handle_command_in_graph(text: str, messages: list, compressor) -> str | None:
    """Handle /commands in the graph context. We mock a minimal MemoryManager."""
    # Create a lightweight wrapper with the interface handle_command needs
    class _MsgStore:
        def __init__(self, msgs):
            self._messages = list(msgs)

        def get_history(self):
            return self._messages

    store = _MsgStore(messages)
    # handle_command expects a MemoryManager; _MsgStore provides get_history()
    try:
        return handle_command(text, store, compressor)
    except Exception:
        return None


def should_end_after_command(state: AgentState) -> str:
    """After command node: if final_response is set, end; otherwise route."""
    if state.get("final_response"):
        return "end"
    return "router"


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("command", command_node)
    builder.add_node("router", classify_intent)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("confirm", confirm_node)

    builder.set_entry_point("command")

    builder.add_conditional_edges(
        "command",
        should_end_after_command,
        {"router": "router", "end": END},
    )

    builder.add_edge("router", "agent")

    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


def get_agent():
    return build_agent_graph()
