from unittest.mock import patch
from langchain_core.messages import HumanMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


def test_graph_builds():
    graph = build_agent_graph()
    assert graph is not None


@patch("src.agent.graph.summarize_node")
def test_graph_routes_planning(mock_summarize):
    mock_summarize.return_value = {"final_response": "你今天有3个会议。"}

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    result = graph.invoke(state)
    assert "final_response" in result
    assert result["final_response"] == "你今天有3个会议。"
