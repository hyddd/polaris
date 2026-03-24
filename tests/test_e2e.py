"""端到端冒烟测试 — 验证完整链路可运行。"""
from unittest.mock import patch
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


@patch("src.agent.graph.agent_node")
def test_e2e_daily_planning(mock_agent):
    mock_agent.return_value = {"messages": [AIMessage(content="你今天有3个会议。")]}
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result


@patch("src.agent.graph.agent_node")
def test_e2e_knowledge_search(mock_agent):
    mock_agent.return_value = {"messages": [AIMessage(content="上次 RBAC 讨论决定采用角色继承模型。")]}
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="上次RBAC讨论了什么")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result


@patch("src.agent.graph.agent_node")
def test_e2e_quick_capture(mock_agent):
    mock_agent.return_value = {"messages": [AIMessage(content="已记录笔记：今天讨论了 LangGraph 方案。")]}
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="记一下：今天讨论了LangGraph方案")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result


@patch("src.agent.graph.agent_node")
def test_e2e_chat(mock_agent):
    mock_agent.return_value = {"messages": [AIMessage(content="你好！我是 Polaris。")]}
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="你好")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result
