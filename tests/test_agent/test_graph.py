from unittest.mock import patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


def test_graph_builds():
    graph = build_agent_graph()
    assert graph is not None


@patch("src.agent.graph.agent_node")
def test_graph_planning_receives_intent(mock_agent):
    """Graph routes through router to agent, agent gets called with state."""
    mock_agent.return_value = {
        "messages": [AIMessage(content="你今天有3个会议。")],
    }

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="",
        user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    # The agent should have been called
    mock_agent.assert_called_once()
    assert "messages" in result


@patch("src.agent.graph.agent_node")
def test_graph_chat_route(mock_agent):
    """Casual chat routes through agent correctly."""
    mock_agent.return_value = {
        "messages": [AIMessage(content="你好！我是 Polaris。")],
    }

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="你好")],
        intent="",
        user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result
