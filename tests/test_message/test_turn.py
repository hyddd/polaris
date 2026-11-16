"""src.message.turn：一轮对话结束后写回什么。"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.message.turn import (
    TurnRecorder, close_dangling_tool_calls, UNKNOWN_TOOL_RESULT, INTERRUPTED_NOTE,
)


def _ai_call(*ids):
    return AIMessage(content="", tool_calls=[{"name": "todo", "args": {}, "id": i} for i in ids])


def test_close_dangling_adds_unknown_results():
    msgs = [_ai_call("a", "b"), ToolMessage(content="ok", tool_call_id="a")]
    out = close_dangling_tool_calls(msgs)
    assert [type(m).__name__ for m in out] == ["AIMessage", "ToolMessage", "ToolMessage"]
    assert out[2].tool_call_id == "b" and out[2].content == UNKNOWN_TOOL_RESULT


def test_close_dangling_keeps_complete_sequences():
    msgs = [_ai_call("a"), ToolMessage(content="ok", tool_call_id="a"), AIMessage(content="done")]
    assert close_dangling_tool_calls(msgs) == msgs


def test_completed_turn_uses_full_final_state():
    base = [HumanMessage(content="h0"), AIMessage(content="a0")]
    human = HumanMessage(content="h1")
    t = TurnRecorder(base, human)
    t.final_state = {"messages": base + [human, AIMessage(content="a1")], "pending_action": None}
    assert [m.content for m in t.history()] == ["h0", "a0", "h1", "a1"]
    assert t.reply_text == "a1"


def test_node_delta_is_not_mistaken_for_full_history():
    """agent 节点的 on_chain_end 只带增量；不能据此覆盖历史。"""
    t = TurnRecorder([HumanMessage(content="h0")], HumanMessage(content="h1"))
    t.feed({"event": "on_chain_end", "name": "agent", "parent_ids": ["root"],
            "metadata": {"langgraph_node": "agent"},
            "data": {"output": {"messages": [AIMessage(content="a1")]}}})
    assert not t.completed
    assert [m.content for m in t.deltas] == ["a1"]


def test_confirm_notice_restores_base():
    base = [HumanMessage(content="h0")]
    t = TurnRecorder(base, HumanMessage(content="确认"))
    t.final_state = {"messages": [], "final_response": "已删除", "pending_action": None}
    assert t.history() == base
    assert t.notice == "已删除"


def test_interrupted_with_partial_text():
    t = TurnRecorder([], HumanMessage(content="h"))
    t.feed({"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="半句")}})
    hist = t.history()
    assert hist[0].content == "h"
    assert hist[-1].content == f"半句\n\n{INTERRUPTED_NOTE}"


def test_interrupted_with_nothing_rolls_back():
    base = [HumanMessage(content="h0")]
    assert TurnRecorder(base, HumanMessage(content="h1")).history() == base


def test_pending_action_from_nodes_when_interrupted():
    t = TurnRecorder([], HumanMessage(content="h"))
    t.feed({"event": "on_chain_end", "name": "tools", "parent_ids": ["root"],
            "metadata": {"langgraph_node": "tools"},
            "data": {"output": {"messages": [], "pending_action": {"x": 1}}}})
    assert t.pending_action() == {"x": 1}
