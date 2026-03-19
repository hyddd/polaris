from langchain_core.messages import HumanMessage
from src.agent.skills.manage import manage_node
from src.state import AgentState


def test_manage_node():
    state = AgentState(
        messages=[HumanMessage(content="取消明天的产品评审")],
        intent="manage", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = manage_node(state)
    assert "manage" in str(result["tool_results"]["mode"])
