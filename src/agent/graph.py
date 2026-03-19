from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.summarize import summarize_node

from src.agent.skills.planning import planning_node
from src.agent.skills.prep import prep_node
from src.agent.skills.search import search_node
from src.agent.skills.capture import capture_node
from src.agent.skills.manage import manage_node


def chat_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {"user_query": last_msg, "mode": "chat"},
        "final_response": "",
    }


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("router", classify_intent)
    builder.add_node("chat", chat_node)
    builder.add_node("planning", planning_node)
    builder.add_node("prep", prep_node)
    builder.add_node("search", search_node)
    builder.add_node("capture", capture_node)
    builder.add_node("manage", manage_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("summarize", summarize_node)

    builder.set_entry_point("router")

    builder.add_conditional_edges(
        "router",
        route_condition,
        {
            "daily_planning": "planning",
            "meeting_prep": "prep",
            "knowledge_search": "search",
            "quick_capture": "capture",
            "manage": "manage",
            "clarify": "chat",
            "chat": "chat",
        }
    )

    for node in ["planning", "prep", "search", "capture", "manage", "chat"]:
        builder.add_edge(node, "summarize")

    builder.add_edge("summarize", END)

    return builder.compile()


def get_agent():
    return build_agent_graph()
