from langchain_core.messages import HumanMessage
from src.agent.skills.planning import planning_node
from src.state import AgentState


def test_planning_node():
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="daily_planning",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    result = planning_node(state)
    assert "tool_results" in result
