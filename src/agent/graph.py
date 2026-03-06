from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.summarize import summarize_node
from src.agent.skills.planning import planning_node


def clarify_node(state: AgentState) -> dict:
    return {
        "final_response": (
            "不太确定你想做什么，能再说详细一点吗？\n"
            "- 「今天有什么安排」查看日程\n"
            "- 「下午3点的会帮我准备」会议准备\n"
            "- 「上次RBAC讨论了什么」搜索笔记\n"
            "- 「记一下：xxx」快速记录\n"
            "- 「取消明天的晨会」管理操作"
        ),
        "needs_clarification": False,
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

    # Core nodes
    builder.add_node("router", classify_intent)
    builder.add_node("clarify", clarify_node)
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
            "clarify": "clarify",
        }
    )

    for node in ["planning", "default"]:
        builder.add_edge(node, "summarize")

    builder.add_edge("clarify", END)
    builder.add_edge("summarize", END)

    return builder.compile()


def get_agent():
    return build_agent_graph()
