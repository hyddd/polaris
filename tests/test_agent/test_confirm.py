"""删除确认：同一轮只确认一次；多个删除合并确认、一起执行；取消不执行。"""
from unittest.mock import patch, MagicMock

from langchain_core.messages import HumanMessage, AIMessage

from src.agent.executor import UNIFIED_SYSTEM_PROMPT, tool_node
from src.agent.graph import confirm_node


def _ai_with_calls(*calls):
    msg = AIMessage(content="")
    tcs = []
    for i, (name, args) in enumerate(calls):
        tc = MagicMock()
        tc.name, tc.args, tc.id = name, args, f"call_{i}"
        tcs.append(tc)
    msg.tool_calls = tcs
    return msg


def _run_tool_node(*calls, invoke_result="ok"):
    with patch("src.agent.executor.ToolRegistry") as reg:
        tool = MagicMock()
        tool.invoke.return_value = invoke_result
        reg.get_instance.return_value.get.return_value = tool
        result = tool_node({"messages": [_ai_with_calls(*calls)]})
    return result, tool


def test_prompt_no_longer_asks_model_to_confirm_first():
    """模型不再先自己问一次（代码拦截会请用户确认）。"""
    assert "删除操作先确认再执行" not in UNIFIED_SYSTEM_PROMPT
    assert "不要自己再询问确认" in UNIFIED_SYSTEM_PROMPT


def test_delete_intercepted_with_readable_description():
    result, tool = _run_tool_node(("todo", {"action": "delete", "todo_id": "todo-1"}))
    pending = result["pending_action"]
    assert pending["action_type"] == "delete" and len(pending["actions"]) == 1
    action = pending["actions"][0]
    assert (action["target_tool"], action["params"]["todo_id"], action["tool_call_id"]) == ("todo", "todo-1", "call_0")
    assert "等待用户确认" in result["messages"][0].content and "不要再次调用删除" in result["messages"][0].content
    tool.invoke.assert_not_called()


def test_reminder_delete_is_intercepted_notes_archive_is_not():
    result, _ = _run_tool_node(("reminder", {"action": "delete", "reminder_id": "rmd-1"}))
    assert result["pending_action"]["actions"][0]["target_tool"] == "reminder"
    result, tool = _run_tool_node(("notes", {"action": "archive", "filename": "a.md"}), invoke_result="已归档")
    assert "pending_action" not in result and tool.invoke.called


def test_batch_deletes_merged_into_one_confirmation():
    """清掉多条日程：全部拦下，合并成一次确认；同一批里的查询照常执行。"""
    result, tool = _run_tool_node(
        ("calendar", {"action": "list", "date": "2026-11-17"}),
        ("calendar", {"action": "delete", "event_id": "evt-1"}),
        ("calendar", {"action": "delete", "event_id": "evt-2"}),
        invoke_result="日程列表")
    assert [a["params"]["event_id"] for a in result["pending_action"]["actions"]] == ["evt-1", "evt-2"]
    tool.invoke.assert_called_once_with({"action": "list", "date": "2026-11-17"})   # 只执行了查询


def test_confirm_executes_all_pending_actions_once():
    pending = {"action_type": "delete", "actions": [
        {"target_tool": "calendar", "params": {"action": "delete", "event_id": "evt-1"}, "description": "日程 A"},
        {"target_tool": "calendar", "params": {"action": "delete", "event_id": "evt-2"}, "description": "日程 B"},
    ]}
    with patch("src.agent.graph.ToolRegistry") as reg:
        tool = MagicMock()
        tool.invoke.side_effect = ["已删除日程：evt-1", "未找到日程：evt-2"]
        reg.get_instance.return_value.get.return_value = tool
        result = confirm_node({"messages": [HumanMessage(content="确认。")], "pending_action": pending})
    assert result["pending_action"] is None
    assert result["final_response"] == "已删除日程 A\n删除日程 B失败：未找到日程：evt-2"
    assert tool.invoke.call_count == 2


def test_confirm_accepts_common_replies_and_old_format():
    old_format = {"target_tool": "todo", "params": {"action": "delete", "todo_id": "todo-1"}}
    for reply in ("确认", "好的", "可以", "OK", "确认删除！"):
        with patch("src.agent.graph.ToolRegistry") as reg:
            tool = MagicMock()
            tool.invoke.return_value = "已删除待办：todo-1"
            reg.get_instance.return_value.get.return_value = tool
            result = confirm_node({"messages": [HumanMessage(content=reply)], "pending_action": old_format})
        assert result["final_response"] == "已删除待办：todo-1", reply


def test_cancel_and_other_input():
    pending = {"action_type": "delete", "actions": [{"target_tool": "todo", "params": {}, "description": "x"}]}
    result = confirm_node({"messages": [HumanMessage(content="算了")], "pending_action": pending})
    assert result["pending_action"] is None and "已取消" in result["final_response"]
    result = confirm_node({"messages": [HumanMessage(content="帮我看看明天的日程")], "pending_action": pending})
    assert result.get("pending_action") is None and not result.get("final_response")


def test_non_delete_executes_normally():
    result, tool = _run_tool_node(("todo", {"action": "list"}), invoke_result="待办列表为空")
    assert "pending_action" not in result and "待办列表为空" in result["messages"][0].content
