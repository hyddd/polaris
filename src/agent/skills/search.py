from langgraph.graph import StateGraph, END
from src.state import AgentState


def search_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {
            "mode": "knowledge_search",
            "instruction": "使用 RAG 语义搜索查找用户提到的内容",
            "tools_available": "rag_search <查询关键词>",
            "user_query": last_msg,
        },
        "final_response": "",
    }


def create_search_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("search", search_node)
    builder.set_entry_point("search")
    builder.add_edge("search", END)
    return builder.compile()
