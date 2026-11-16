"""Tests for src.core.infra.lock — per-session locking."""

import asyncio
import threading
import time

import pytest

import src.core.infra.lock as lock_mod
from src.core.infra.lock import (
    get_session_lock, hold_session_lock, cleanup_session_locks, SessionBusyError,
)


@pytest.fixture(autouse=True)
def _clear_locks():
    lock_mod._message_locks.clear()
    yield
    lock_mod._message_locks.clear()


def test_acquire_and_release():
    """Lock can be acquired and released without error."""
    lck = get_session_lock("sess1")
    assert lck.acquire(timeout=1) is True
    lck.release()

    # 同一 key 返回同一个 lock 实例
    assert get_session_lock("sess1") is lck


def test_lock_is_per_session_not_per_channel():
    """G03：锁只按会话区分。以前按 channel+session，Web 和 QQ 操作同一会话拿到的是两把锁。"""
    assert get_session_lock("sess1") is get_session_lock("sess1")
    assert get_session_lock("sess1") is not get_session_lock("sess2")


def test_concurrent_first_access_creates_single_lock():
    """多线程同时首次获取同一会话的锁，只能建出一把。"""
    barrier = threading.Barrier(16)
    got = []

    def worker():
        barrier.wait()
        got.append(get_session_lock("race"))

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert len({id(lck) for lck in got}) == 1


def test_concurrent_access():
    """Concurrent threads are mutually excluded by the lock."""
    lck = get_session_lock("sess1")
    entered = []
    barrier = threading.Barrier(2, timeout=3)

    def worker(tag):
        with lck:
            entered.append(f"{tag}_start")
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            entered.append(f"{tag}_end")

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(entered) == 4
    assert entered[0].split("_")[0] == entered[1].split("_")[0]


def test_hold_session_lock_waits_without_blocking_event_loop():
    """②：等锁期间事件循环必须继续转，持锁方才能往下执行并释放锁。

    旧代码在 async 函数里阻塞式 acquire，持锁方需要同一个事件循环才能释放 → 永久死锁。
    整个场景放在独立线程里跑，回归时测试会以超时失败，而不是把 pytest 一起卡死。
    """
    result = {}

    async def scenario():
        ticks = 0
        holder_released = asyncio.Event()

        async def holder():
            async with hold_session_lock("s"):
                # 持锁期间需要事件循环继续工作（模拟流式回复在 await 模型）
                await asyncio.sleep(0.3)
            holder_released.set()

        async def waiter():
            async with hold_session_lock("s", timeout=5):
                return holder_released.is_set()

        async def ticker():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(0.02)
                ticks += 1

        h = asyncio.create_task(holder())
        await asyncio.sleep(0.05)
        got_after_release, _, _ = await asyncio.gather(waiter(), ticker(), h)
        result["ticks"] = ticks
        result["waiter_ran_after_holder"] = got_after_release

    t = threading.Thread(target=lambda: asyncio.run(scenario()), daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "事件循环被阻塞：等锁卡住了持锁方"
    assert result["ticks"] == 10
    assert result["waiter_ran_after_holder"] is True


def test_hold_session_lock_timeout_raises_busy():
    lck = get_session_lock("busy")
    lck.acquire()
    try:
        async def run():
            async with hold_session_lock("busy", timeout=0.2):
                pass
        start = time.monotonic()
        with pytest.raises(SessionBusyError):
            asyncio.run(run())
        assert time.monotonic() - start < 2
    finally:
        lck.release()


def test_hold_session_lock_cancel_while_waiting_does_not_leak():
    """等锁时被取消：还没拿到锁，不能留下一把永远不释放的锁。"""
    lck = get_session_lock("c")
    lck.acquire()

    async def _enter(sid):
        async with hold_session_lock(sid):
            pass

    async def run():
        task = asyncio.create_task(_enter("c"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    lck.release()
    assert lck.acquire(blocking=False) is True
    lck.release()


def test_hold_session_lock_releases_on_exception():
    async def run():
        with pytest.raises(RuntimeError):
            async with hold_session_lock("e"):
                raise RuntimeError("boom")

    asyncio.run(run())
    assert get_session_lock("e").acquire(blocking=False) is True


def test_cleanup_session_locks():
    get_session_lock("u1")
    get_session_lock("u2")

    cleanup_session_locks("u1")

    assert "u1" not in lock_mod._message_locks
    assert "u2" in lock_mod._message_locks
