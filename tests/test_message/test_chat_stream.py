"""流式聊天路由（/api/chat/stream）的回归测试。

用真实的 chat_stream 路由 + 真实编译的 LangGraph（只替换节点为脚本），验证落盘语义。
"""
import asyncio
import json
import threading
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import src.session.manager as manager_mod
from src.core.infra.lock import get_session_lock
from src.message.turn import UNKNOWN_TOOL_RESULT, INTERRUPTED_NOTE

from ._fakes import Script, tool_call, run_stream, open_stream, parse_sse, contents


def _disk_messages(session_id):
    data = json.loads((manager_mod.SESSIONS_DIR / f"{session_id}.json").read_text(encoding="utf-8"))
    return [(m["type"], m["content"]) for m in data["messages"]], data


# ---------------------------------------------------------------------------
# 新发现：每轮流式对话把历史覆盖成只剩最后一条 AI 回复
# ---------------------------------------------------------------------------

def test_history_accumulates_across_turns(session_mgr):
    """旧代码把 agent 节点的增量输出当完整历史，3 轮后历史只剩 ['回复3']。"""
    script = Script([AIMessage(content="回复1"), AIMessage(content="回复2"), AIMessage(content="回复3")])
    graph = script.build()

    async def scenario():
        for text in ["第一句", "第二句", "第三句"]:
            await run_stream(graph, text)

    asyncio.run(scenario())
    session = session_mgr.active_session("admin")
    assert contents(session.memory.get_messages()) == [
        "第一句", "回复1", "第二句", "回复2", "第三句", "回复3",
    ]
    on_disk, _ = _disk_messages(session.session_id)
    assert [c for _, c in on_disk] == ["第一句", "回复1", "第二句", "回复2", "第三句", "回复3"]


def test_tool_turn_persists_full_chain(session_mgr):
    script = Script([tool_call(), AIMessage(content="你有 0 条待办")], tool_result="[]")
    asyncio.run(run_stream(script.build(), "看看待办"))
    msgs = session_mgr.active_session("admin").memory.get_messages()
    assert [m.type for m in msgs] == ["human", "ai", "tool", "ai"]
    assert msgs[-1].content == "你有 0 条待办"


# ---------------------------------------------------------------------------
# G01：done 必须在落盘之后发
# ---------------------------------------------------------------------------

def test_done_is_sent_after_session_saved(session_mgr):
    script = Script([AIMessage(content="已保存的回复")])
    sid = session_mgr.active_session("admin").session_id
    seen_on_done = {}

    def on_frame(frame):
        if frame[0] == "done":
            seen_on_done["disk"], _ = _disk_messages(sid)

    asyncio.run(run_stream(script.build(), "你好", on_frame=on_frame))
    assert ("ai", "已保存的回复") in seen_on_done["disk"]


# ---------------------------------------------------------------------------
# G02：拿不到锁时不能往历史里写任何东西
# ---------------------------------------------------------------------------

def test_busy_session_leaves_history_untouched(session_mgr):
    session = session_mgr.active_session("admin")
    session.memory.add_message(HumanMessage(content="旧消息"))
    lock = get_session_lock(session.session_id)
    lock.acquire()
    try:
        frames = asyncio.run(run_stream(Script([]).build(), "这条不该留下"))
    finally:
        lock.release()
    assert frames[0][0] == "error" and "正在处理中" in frames[0][1]["error"]
    assert frames[-1][0] == "done"
    assert contents(session.memory.get_messages()) == ["旧消息"]


# ---------------------------------------------------------------------------
# G08：确认/取消的结果要发给客户端，且不残留记忆、pending_action 要落盘清空
# ---------------------------------------------------------------------------

def test_cancel_confirmation_is_sent_and_not_kept(session_mgr):
    session = session_mgr.active_session("admin")
    session.memory.add_message(HumanMessage(content="删掉待办 A"))
    session.memory.add_message(AIMessage(content="确认删除待办 A 吗？"))
    session.pending_action = {"target_tool": "todo", "params": {"action": "delete", "id": "A"}}

    frames = asyncio.run(run_stream(Script([]).build(), "取消"))

    assert ("message", {"content": "已取消操作。"}) in frames
    assert contents(session.memory.get_messages()) == ["删掉待办 A", "确认删除待办 A 吗？"]
    assert session.pending_action is None
    _, data = _disk_messages(session.session_id)
    assert data["pending_action"] is None


def test_confirm_executes_and_result_is_sent(session_mgr):
    class StubTool:
        def invoke(self, params):
            return f"已删除待办 {params['id']}"

    class StubRegistry:
        def get(self, name):
            return StubTool()

    session = session_mgr.active_session("admin")
    session.pending_action = {"target_tool": "todo", "params": {"action": "delete", "id": "A"}}
    with patch("src.agent.graph.ToolRegistry.get_instance", return_value=StubRegistry()):
        frames = asyncio.run(run_stream(Script([]).build(), "确认"))
    assert ("message", {"content": "已删除待办 A"}) in frames
    assert session.pending_action is None


# ---------------------------------------------------------------------------
# 中断：客户端断开时也要落盘；工具已生效要留痕，未完成的工具调用标“结果未知”
# ---------------------------------------------------------------------------

def _run_and_cancel_during_tool(graph, script, cancel_mode):
    async def scenario():
        body = await open_stream(graph, "帮我建个待办")

        async def consume():
            async for _ in body:
                pass

        task = asyncio.create_task(consume())
        # 等工具真正开始执行（在线程池里阻塞着）
        await asyncio.to_thread(script.tool_started.wait, 5)
        if cancel_mode == "cancel":
            # Starlette 在客户端断开时取消整个响应任务
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        script.tool_release.set()
        await asyncio.sleep(0.2)

    asyncio.run(scenario())


def test_disconnect_during_tool_persists_trace(session_mgr):
    script = Script([tool_call(), AIMessage(content="不会走到这里")], block_tools=True)
    _run_and_cancel_during_tool(script.build(), script, "cancel")

    session = session_mgr.active_session("admin")
    msgs = session.memory.get_messages()
    assert [m.type for m in msgs] == ["human", "ai", "tool", "ai"]
    assert msgs[1].tool_calls[0]["id"] == "call_1"
    assert isinstance(msgs[2], ToolMessage) and msgs[2].content == UNKNOWN_TOOL_RESULT
    assert INTERRUPTED_NOTE in msgs[3].content
    on_disk, _ = _disk_messages(session.session_id)
    assert [t for t, _ in on_disk] == ["human", "ai", "tool", "ai"]
    # 锁已释放
    assert get_session_lock(session.session_id).acquire(blocking=False)


def test_client_closes_stream_at_yield_persists(session_mgr):
    """GeneratorExit 路径：客户端拿到第一段 token 后关闭连接。"""
    script = Script([AIMessage(content="一段比较长的回复内容")])

    async def scenario():
        body = await open_stream(script.build(), "你好")
        first = await body.__anext__()
        assert parse_sse(first)[0][1].get("token")
        await body.aclose()

    asyncio.run(scenario())
    session = session_mgr.active_session("admin")
    msgs = session.memory.get_messages()
    assert msgs[0].content == "你好"
    assert msgs[-1].type == "ai" and INTERRUPTED_NOTE in msgs[-1].content
    on_disk, _ = _disk_messages(session.session_id)
    assert on_disk[0] == ("human", "你好")


def test_interrupt_before_anything_happens_rolls_back(session_mgr):
    """还没有任何输出和工具调用就断开：整轮回滚，相当于没发过。"""
    gate = threading.Event()
    script = Script([AIMessage(content="x")])
    original = script.agent_node

    def slow_agent(state):
        gate.wait(5)
        return original(state)

    script.agent_node = slow_agent
    graph = script.build()

    async def scenario():
        body = await open_stream(graph, "算了")
        task = asyncio.create_task(body.__anext__())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, StopAsyncIteration):
            pass
        gate.set()
        await asyncio.sleep(0.1)

    asyncio.run(scenario())
    assert session_mgr.active_session("admin").memory.get_messages() == []


def test_error_mid_run_keeps_tool_trace_and_reports(session_mgr):
    script = Script([tool_call()])  # 第二次调用 agent 时脚本越界 → IndexError
    frames = asyncio.run(run_stream(script.build(), "建待办"))
    assert any(e == "error" for e, _ in frames)
    assert frames[-1][0] == "done"
    msgs = session_mgr.active_session("admin").memory.get_messages()
    assert [m.type for m in msgs] == ["human", "ai", "tool", "ai"]
    assert msgs[2].content == "工具执行成功"
    assert "本轮处理出错" in msgs[3].content


# ---------------------------------------------------------------------------
# 会话固定：运行中切换 channel 的激活会话，结果仍写回原会话
# ---------------------------------------------------------------------------

def test_result_goes_to_session_where_turn_started(session_mgr):
    a = session_mgr.active_session("admin")
    b = session_mgr.create(name="另一个")
    script = Script([tool_call(), AIMessage(content="完成")], block_tools=True)
    graph = script.build()

    async def scenario():
        task = asyncio.create_task(run_stream(graph, "在 A 里说的话"))
        await asyncio.to_thread(script.tool_started.wait, 5)
        session_mgr.switch(b.session_id, "admin")   # 运行中把网页切到 B
        script.tool_release.set()
        await task

    asyncio.run(scenario())
    assert contents(a.memory.get_messages())[0] == "在 A 里说的话"
    assert b.memory.get_messages() == []


# ---------------------------------------------------------------------------
# G12 并发部分：运行中到点的提醒不会被本轮写回覆盖
# ---------------------------------------------------------------------------

def test_reminder_pushed_during_turn_is_preserved(session_mgr):
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.models import Reminder
    from datetime import datetime

    session = session_mgr.active_session("admin")
    script = Script([tool_call(), AIMessage(content="完成")], block_tools=True)
    graph = script.build()
    reminder = Reminder(title="开会", trigger_time=datetime.now(), channel="admin",
                        session_id=session.session_id)

    async def scenario():
        task = asyncio.create_task(run_stream(graph, "帮我查待办"))
        await asyncio.to_thread(script.tool_started.wait, 5)
        # APScheduler 线程里触发提醒
        await asyncio.to_thread(ReminderHandler([]).handle, reminder)
        script.tool_release.set()
        await task

    asyncio.run(scenario())
    texts = contents(session.memory.get_messages())
    assert "⏰ 提醒：开会" in texts
    assert texts[0] == "帮我查待办" and "完成" in texts
    on_disk, _ = _disk_messages(session.session_id)
    assert ("ai", "⏰ 提醒：开会") in on_disk
