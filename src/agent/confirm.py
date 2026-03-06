from src.state import AgentState


def confirm_node(state: AgentState) -> dict:
    pending = state.get("pending_action")
    if not pending:
        return {"final_response": "没有待确认的操作。", "pending_action": None}

    messages = state.get("messages", [])
    last_msg = messages[-1].content.strip() if messages else ""

    if last_msg in ("确认", "是", "yes", "好", "可以", "ok"):
        return {"final_response": "", "pending_action": {**pending, "confirmed": True}}

    if last_msg in ("取消", "不", "no", "算了", "别"):
        return {"final_response": "已取消操作。", "pending_action": None}

    return {"final_response": f"请确认：{pending.get('description', '执行此操作？')}（回复「确认」或「取消」）"}
