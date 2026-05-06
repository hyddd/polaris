"""Tests for src.core.events.EventBus."""

import asyncio
import time

from src.core.infra.events import EventBus


def _wait():
    """Give the background event loop time to dispatch."""
    time.sleep(0.1)


def test_subscribe_and_publish():
    bus = EventBus()
    called = []
    bus.subscribe("hello", lambda: called.append(True))
    bus.publish("hello")
    _wait()
    assert called == [True]


def test_publish_with_payload():
    bus = EventBus()
    received = {}
    bus.subscribe("msg", lambda text, count: received.update({"text": text, "count": count}))
    bus.publish("msg", text="hi", count=42)
    _wait()
    assert received == {"text": "hi", "count": 42}


def test_publish_no_subscribers():
    bus = EventBus()
    # 不应抛出异常
    bus.publish("nonexistent", data=1)


def test_handler_exception_isolation():
    bus = EventBus()
    called = []

    def bad_handler():
        raise ValueError("boom")

    def good_handler():
        called.append("ok")

    bus.subscribe("evt", bad_handler)
    bus.subscribe("evt", good_handler)
    bus.publish("evt")
    _wait()
    assert called == ["ok"]


def test_multiple_handlers():
    bus = EventBus()
    results = []
    bus.subscribe("evt", lambda: results.append("a"))
    bus.subscribe("evt", lambda: results.append("b"))
    bus.subscribe("evt", lambda: results.append("c"))
    bus.publish("evt")
    _wait()
    assert results == ["a", "b", "c"]


def test_publish_async_handler():
    bus = EventBus()
    called = []

    async def handler(text):
        called.append(text)

    bus.subscribe("msg", handler)
    bus.publish("msg", text="async-hello")
    _wait()
    assert called == ["async-hello"]


def test_publish_mixed_handlers():
    bus = EventBus()
    results = []

    def sync_h():
        results.append("sync")

    async def async_h():
        results.append("async")

    bus.subscribe("evt", sync_h)
    bus.subscribe("evt", async_h)
    bus.publish("evt")
    _wait()
    assert "sync" in results
    assert "async" in results


def test_publish_does_not_block():
    bus = EventBus()

    def slow_handler():
        time.sleep(0.5)

    bus.subscribe("slow", slow_handler)
    start = time.monotonic()
    bus.publish("slow")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # publish returns immediately
