"""统一消息入口（router.process_message）的回归测试：QQ / 飞书 / 心跳 / 非流式 /api/chat 都走这里。"""
import asyncio
import threading
import time

import pytest
from langchain_core.messages import AIMessage

import src.message.router as router
from src.core.infra.lock import get_session_lock
from src.message import process_message

from ._fakes import Script, tool_call, run_stream, contents


@pytest.fixture
def use_graph(monkeypatch):
    """整个测试期间让 router 用指定的图。不能在并发协程里各自 patch：
    先结束的协程会把补丁撤掉，后一个就拿到了真实 agent。"""
    def _use(graph):
        monkeypatch.setattr(router, "get_agent", lambda: graph)
        return graph
    return _use


def _process(graph, text, mgr, channel):
    return process_message(text, mgr, channel=channel)


def test_rename_during_streaming_reply_does_not_freeze_server(session_mgr, use_graph):
    """② 原始场景：网页回复还在流式输出时，去会话页重命名。

    旧代码：router 在事件循环线程里阻塞式 acquire 同一把锁 → 整个服务永久卡死。
    现在：重命名等到回复结束后执行，期间事件循环照常工作。
    场景在独立线程里跑，回归时以超时失败而不是卡死 pytest。
    """
    script = Script([tool_call(), AIMessage(content="完成")], block_tools=True)
    graph = use_graph(script.build())
    result = {}

    async def scenario():
        ticks = 0
        stream = asyncio.create_task(run_stream(graph, "查一下待办"))
        await asyncio.to_thread(script.tool_started.wait, 5)

        rename = asyncio.create_task(_process(graph, "/rename 新名字", session_mgr, "admin"))

        async def ticker():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(0.02)
                ticks += 1

        await ticker()
        assert not rename.done(), "重命名应该在等锁"
        script.tool_release.set()
        await stream
        result["rename"] = await asyncio.wait_for(rename, 5)
        result["ticks"] = ticks

    t = threading.Thread(target=lambda: asyncio.run(scenario()), daemon=True)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), "服务卡死：重命名阻塞了事件循环"
    assert result["ticks"] == 10
    assert "已重命名" in result["rename"][-1][0]
    assert session_mgr.active_session("admin").name == "新名字"


def test_same_session_from_two_channels_is_serialized(session_mgr, use_graph):
    """G03：网页（主事件循环）和 QQ（自己的线程 + 事件循环）同时操作同一个会话。

    旧代码锁按 channel 区分，两边并发执行，后保存的一方把另一方这一轮整个覆盖掉。
    现在 QQ 要等网页这一轮结束才执行，两轮都完整保留。
    """
    session = session_mgr.active_session("admin")
    session_mgr.switch(session.session_id, "qq:u1")   # QQ 也切到同一个会话

    web = Script([tool_call(), AIMessage(content="网页的答复")], block_tools=True)
    web_graph = web.build()
    use_graph(Script([AIMessage(content="QQ 的答复")]).build())
    qq_result = []

    def qq_thread():
        qq_result.append(asyncio.run(process_message("QQ 的问题", session_mgr, channel="qq:u1")))

    async def scenario():
        stream = asyncio.create_task(run_stream(web_graph, "网页的问题"))
        await asyncio.to_thread(web.tool_started.wait, 5)
        t = threading.Thread(target=qq_thread, daemon=True)
        t.start()
        await asyncio.sleep(0.3)
        qq_waited = not qq_result          # 网页这一轮没结束前，QQ 不该已经完成
        web.tool_release.set()
        await stream
        await asyncio.to_thread(t.join, 10)
        return qq_waited

    try:
        qq_waited = asyncio.run(scenario())
    finally:
        web.tool_release.set()   # 断言失败时也放行被挡住的工具线程，避免测试挂死
    assert qq_waited, "QQ 没有等网页这一轮结束就并发执行了"
    texts = contents(session.memory.get_messages())
    assert texts[0] == "网页的问题" and "网页的答复" in texts
    assert texts[-2:] == ["QQ 的问题", "QQ 的答复"]


def test_router_does_not_block_event_loop_while_model_runs(session_mgr, use_graph):
    """agent 改为 ainvoke：模型调用期间事件循环照常处理其他请求。

    旧代码同步 agent.invoke 期间整个事件循环停住，模型调用结束时 ticker 一次都没跑过。
    """
    ticks = 0
    ticks_when_model_done = []

    def slow_agent(state):
        time.sleep(0.3)
        ticks_when_model_done.append(ticks)
        return {"messages": [AIMessage(content="好")]}

    script = Script([])
    script.agent_node = slow_agent
    graph = use_graph(script.build())

    async def scenario():
        nonlocal ticks

        async def ticker():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(0.02)
                ticks += 1

        await asyncio.gather(_process(graph, "你好", session_mgr, "admin"), ticker())

    asyncio.run(scenario())
    assert ticks_when_model_done and ticks_when_model_done[0] >= 3


def test_router_busy_timeout_returns_message(session_mgr, monkeypatch, use_graph):
    monkeypatch.setattr(router, "LOCK_WAIT_SECONDS", 0.2)
    session = session_mgr.active_session("qq:u1")
    lock = get_session_lock(session.session_id)
    lock.acquire()
    try:
        result = asyncio.run(_process(use_graph(Script([]).build()), "你好", session_mgr, "qq:u1"))
    finally:
        lock.release()
    assert result == [(router.BUSY_REPLY, [])]
    assert session.memory.get_messages() == []


def test_router_persists_full_history(session_mgr, use_graph):
    graph = use_graph(Script([AIMessage(content="一"), AIMessage(content="二")]).build())

    async def scenario():
        await _process(graph, "甲", session_mgr, "qq:u1")
        await _process(graph, "乙", session_mgr, "qq:u1")

    asyncio.run(scenario())
    session = session_mgr.active_session("qq:u1")
    assert contents(session.memory.get_messages()) == ["甲", "一", "乙", "二"]
    assert session.metadata["message_count"] == 4


def test_router_result_goes_to_locked_session_even_if_switched_while_waiting(session_mgr, use_graph):
    """等锁期间 channel 的激活会话被切走：消息仍写进最初加锁的会话。"""
    a = session_mgr.active_session("qq:u1")
    b = session_mgr.create(name="B")
    graph = use_graph(Script([AIMessage(content="回复")]).build())
    lock = get_session_lock(a.session_id)
    lock.acquire()

    async def scenario():
        task = asyncio.create_task(_process(graph, "发给 A 的", session_mgr, "qq:u1"))
        await asyncio.sleep(0.1)
        session_mgr.switch(b.session_id, "qq:u1")
        lock.release()
        await task

    # 旧代码在事件循环里阻塞等锁，release 那一行永远轮不到 → 放进独立线程，回归时超时失败而不是挂死
    t = threading.Thread(target=lambda: asyncio.run(scenario()), daemon=True)
    t.start()
    t.join(timeout=10)
    if t.is_alive():
        lock.release()
        t.join(timeout=5)
        raise AssertionError("事件循环被阻塞：router 在事件循环里阻塞式等锁")
    assert contents(a.memory.get_messages()) == ["发给 A 的", "回复"]
    assert b.memory.get_messages() == []
