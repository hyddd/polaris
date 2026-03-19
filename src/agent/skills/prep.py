from langgraph.graph import StateGraph, END
from src.state import AgentState


def prep_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {
            "mode": "meeting_prep",
            "instruction": "按步骤操作：1.查日历找会议 2.搜相关笔记 3.查关联待办 4.汇总准备清单",
            "tools_available": "calendar search <关键词>, rag_search <关键词>, todo search <关键词>",
            "user_query": last_msg,
        },
        "final_response": "",
    }


def create_prep_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("prep", prep_node)
    builder.set_entry_point("prep")
    builder.add_edge("prep", END)
    return builder.compile()
