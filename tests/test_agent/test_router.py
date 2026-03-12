from langchain_core.messages import HumanMessage
from src.agent.router import classify_intent
from src.state import AgentState


def make_state(message: str) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=message)],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )


def test_router_daily_planning():
    assert classify_intent(make_state("今天有什么安排"))["intent"] == "daily_planning"


def test_router_meeting_prep():
    assert classify_intent(make_state("下午3点的会帮我准备一下"))["intent"] == "meeting_prep"


def test_router_knowledge_search():
    assert classify_intent(make_state("上次RBAC的讨论结果是什么"))["intent"] == "knowledge_search"


def test_router_quick_capture():
    assert classify_intent(make_state("明天下午3点加个产品评审会"))["intent"] == "quick_capture"


def test_router_manage():
    assert classify_intent(make_state("取消明天的产品评审"))["intent"] == "manage"


def test_router_casual_chat():
    assert classify_intent(make_state("你好"))["intent"] == "chat"


def test_router_self_intro():
    assert classify_intent(make_state("你是谁"))["intent"] == "chat"


def test_router_defaults_to_chat():
    assert classify_intent(make_state("..."))["intent"] == "chat"
