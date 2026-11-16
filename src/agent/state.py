from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class PendingAction(TypedDict, total=False):
    action_type: str  # "create" | "update" | "delete"
    target_tool: str  # "calendar" | "todo" | "notes"
    target_id: str
    description: str
    params: dict


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    user_profile: dict
    tool_results: dict
    final_response: str
    needs_clarification: bool
    pending_action: Optional[dict]
    streaming: bool  # True = chain.stream() for token events; False = chain.invoke()
    channel: str  # "admin" | "feishu" | "qq" | "default"
    session_id: str  # 本轮固定执行的会话；运行中 channel 的激活会话可能被切走
