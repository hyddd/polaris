from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.summarize import summarize_node
from src.agent.skills.planning import planning_node


def chat_node(state: AgentState) -> dict:
    """Casual conversation / clarification — pass through to LLM for natural reply."""
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {"user_query": last_msg, "mode": "chat"},
        "final_response": "",
    }


def default_skill_node(state: AgentState) -> dict:
    """Stub node for skills not yet implemented."""
    intent = state.get("intent", "")
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {"user_query": last_msg, "mode": intent},
        "final_response": "",
    }


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("router", classify_intent)
    builder.add_node("chat", chat_node)
    builder.add_node("planning", planning_node)
    builder.add_node("default", default_skill_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("summarize", summarize_node)

    builder.set_entry_point("router")

    builder.add_conditional_edges(
        "router",
        route_condition,
        {
            "daily_planning": "planning",
            "meeting_prep": "default",
            "knowledge_search": "default",
            "quick_capture": "default",
            "manage": "default",
            "clarify": "chat",
            "chat": "chat",
        }
    )

    for node in ["planning", "default", "chat"]:
        builder.add_edge(node, "summarize")

    builder.add_edge("summarize", END)

    return builder.compile()


def get_agent():
    return build_agent_graph()
