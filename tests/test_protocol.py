from src.protocol import AgentRequest, AgentResponse
from src.state import AgentState


def test_agent_request_creation():
    req = AgentRequest(message="今天有什么安排", session_id="sess-123")
    assert req.message == "今天有什么安排"
    assert req.session_id == "sess-123"


def test_agent_response_creation():
    resp = AgentResponse(response="你今天有3个会议", steps=["router: daily_planning", "tool: calendar_query"])
    assert resp.response == "你今天有3个会议"
    assert len(resp.steps) == 2


def test_agent_state_defaults():
    state = AgentState(
        messages=[],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    assert state["intent"] == ""
    assert state["pending_action"] is None
