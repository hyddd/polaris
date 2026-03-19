from langgraph.graph import StateGraph, END
from src.state import AgentState


def manage_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {
            "mode": "manage",
            "instruction": (
                "判断操作类型并调用对应工具：\n"
                "- 查询/搜索：calendar search <关键词> 或 todo search <关键词>\n"
                "- 修改：calendar update <id> <json> 或 todo update <id> <json>\n"
                "- 删除/取消：calendar delete <id> 或 todo delete <id>\n"
                "- 标记完成：todo done <id>\n"
                "重要：修改和删除操作必须先搜索找到目标，回显确认后再执行。"
            ),
            "tools_available": "calendar/search/update/delete, todo/search/done/delete",
            "user_query": last_msg,
        },
        "final_response": "",
    }


def create_manage_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("manage", manage_node)
    builder.set_entry_point("manage")
    builder.add_edge("manage", END)
    return builder.compile()
