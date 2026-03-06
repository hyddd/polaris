from langgraph.graph import StateGraph, END
from src.state import AgentState


def planning_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    return {
        "tool_results": {"user_query": last_msg, "mode": "planning"},
        "final_response": "",
    }


def create_planning_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("planning", planning_node)
    builder.set_entry_point("planning")
    builder.add_edge("planning", END)
    return builder.compile()
