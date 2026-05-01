"""Tests for delete confirmation flow."""
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.agent.executor import tool_node
from src.agent.graph import command_node


def test_tool_node_intercepts_delete():
    """tool_node should set pending_action instead of executing delete."""
    mock_tc = MagicMock()
    mock_tc.name = "todo"
    mock_tc.args = {"action": "delete", "todo_id": "todo-1"}
    mock_tc.id = "call_123"

    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = [mock_tc]

    state = {"messages": [ai_msg]}

    with patch("src.agent.executor.ToolRegistry") as mock_registry_cls:
        mock_tool = MagicMock()
        mock_tool.name = "todo"
        mock_registry_cls.get_instance.return_value.get.return_value = mock_tool

        result = tool_node(state)

    assert "pending_action" in result
    assert result["pending_action"]["action_type"] == "delete"
    assert result["pending_action"]["target_tool"] == "todo"
    assert result["pending_action"]["params"]["todo_id"] == "todo-1"
    assert result["pending_action"]["tool_call_id"] == "call_123"
    # Should return confirmation prompt, not execute
    assert "确认" in result["messages"][0].content


def test_command_node_confirms_pending_action():
    """command_node should execute pending action on '确认'."""
    state = {
        "messages": [HumanMessage(content="确认")],
        "pending_action": {
            "action_type": "delete",
            "target_tool": "todo",
            "target_id": "todo-1",
            "params": {"action": "delete", "todo_id": "todo-1"},
            "tool_call_id": "call_123",
        },
        "final_response": "",
    }

    with patch("src.agent.graph.ToolRegistry") as mock_registry_cls:
        mock_tool = MagicMock()
        mock_tool.invoke.return_value = "已删除待办：完成设计文档"
        mock_registry_cls.get_instance.return_value.get.return_value = mock_tool

        result = command_node(state)

    assert result["pending_action"] is None
    assert "已删除" in result["final_response"]
    mock_tool.invoke.assert_called_once_with({"action": "delete", "todo_id": "todo-1"})


def test_command_node_cancels_pending_action():
    """command_node should clear pending action on '取消'."""
    state = {
        "messages": [HumanMessage(content="取消")],
        "pending_action": {
            "action_type": "delete",
            "target_tool": "todo",
            "target_id": "todo-1",
            "params": {"action": "delete", "todo_id": "todo-1"},
        },
        "final_response": "",
    }

    result = command_node(state)

    assert result["pending_action"] is None
    assert "已取消" in result["final_response"]


def test_command_node_clears_pending_on_other_input():
    """command_node should clear pending action when user says something else."""
    state = {
        "messages": [HumanMessage(content="帮我看看明天的日程")],
        "pending_action": {
            "action_type": "delete",
            "target_tool": "todo",
            "target_id": "todo-1",
            "params": {"action": "delete", "todo_id": "todo-1"},
        },
        "final_response": "",
    }

    result = command_node(state)

    assert result.get("pending_action") is None
    # Should not have final_response — pass through to agent
    assert "final_response" not in result or not result["final_response"]


def test_tool_node_executes_non_delete_normally():
    """tool_node should execute non-delete tool calls without interception."""
    mock_tc = MagicMock()
    mock_tc.name = "todo"
    mock_tc.args = {"action": "list"}
    mock_tc.id = "call_456"

    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = [mock_tc]

    state = {"messages": [ai_msg]}

    with patch("src.agent.executor.ToolRegistry") as mock_registry_cls:
        mock_tool = MagicMock()
        mock_tool.name = "todo"
        mock_tool.invoke.return_value = "待办列表为空"
        mock_registry_cls.get_instance.return_value.get.return_value = mock_tool

        result = tool_node(state)

    assert "pending_action" not in result
    assert "待办列表为空" in result["messages"][0].content
    mock_tool.invoke.assert_called_once()
