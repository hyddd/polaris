from langgraph.graph import StateGraph, END
from src.state import AgentState


def capture_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    return {
        "tool_results": {
            "mode": "quick_capture",
            "instruction": (
                "判断用户想记录的类型并调用对应工具：\n"
                "- 日程（含时间/日期信息）：calendar create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}\n"
                "- 笔记（信息/想法/结论）：notes create {\"title\":\"...\",\"content\":\"...\",\"tags\":[...]}\n"
                "- 待办（任务/事项）：todo create {\"title\":\"...\",\"priority\":\"high|medium|low\",\"due\":\"YYYY-MM-DD\"}\n"
                "将自然语言日期（明天、周五）转换为具体日期。"
            ),
            "tools_available": "calendar create, notes create, todo create",
            "user_query": last_msg,
        },
        "final_response": "",
    }


def create_capture_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("capture", capture_node)
    builder.set_entry_point("capture")
    builder.add_edge("capture", END)
    return builder.compile()
