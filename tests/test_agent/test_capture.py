from langchain_core.messages import HumanMessage
from src.agent.skills.capture import capture_node
from src.state import AgentState


def test_capture_node():
    state = AgentState(
        messages=[HumanMessage(content="明天下午3点加个产品评审会")],
        intent="quick_capture", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = capture_node(state)
    assert "quick_capture" in str(result["tool_results"]["mode"])
