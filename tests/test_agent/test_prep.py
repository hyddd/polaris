from langchain_core.messages import HumanMessage
from src.agent.skills.prep import prep_node
from src.state import AgentState


def test_prep_node():
    state = AgentState(
        messages=[HumanMessage(content="下午3点的会帮我准备")],
        intent="meeting_prep", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = prep_node(state)
    assert "meeting_prep" in str(result["tool_results"]["mode"])
