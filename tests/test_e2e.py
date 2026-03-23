"""端到端冒烟测试 — 验证完整链路可运行。"""
from unittest.mock import patch
from langchain_core.messages import HumanMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


@patch("src.agent.executor.ChatOpenAI")
def test_e2e_daily_planning(mock_llm_class):
    mock_llm = mock_llm_class.return_value
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = HumanMessage(content="你今天有3个会议：晨会、产品评审、周报同步。")

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result
    assert len(result["messages"]) >= 2


@patch("src.agent.executor.ChatOpenAI")
def test_e2e_knowledge_search(mock_llm_class):
    mock_llm = mock_llm_class.return_value
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = HumanMessage(content="搜索结果显示，上次 RBAC 讨论决定采用角色继承模型。")

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="上次RBAC讨论了什么")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result


@patch("src.agent.executor.ChatOpenAI")
def test_e2e_quick_capture(mock_llm_class):
    mock_llm = mock_llm_class.return_value
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = HumanMessage(content="已记录笔记：今天讨论了 LangGraph 方案。")

    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="记一下：今天讨论了LangGraph方案")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "messages" in result
