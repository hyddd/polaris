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
