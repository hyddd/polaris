"""Tests for src.core.events.EventBus."""

from src.core.events import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    called = []
    bus.subscribe("hello", lambda: called.append(True))
    bus.publish("hello")
    assert called == [True]


def test_publish_with_payload():
    bus = EventBus()
    received = {}
    bus.subscribe("msg", lambda text, count: received.update({"text": text, "count": count}))
    bus.publish("msg", text="hi", count=42)
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
    assert called == ["ok"]


def test_multiple_handlers():
    bus = EventBus()
    results = []
    bus.subscribe("evt", lambda: results.append("a"))
    bus.subscribe("evt", lambda: results.append("b"))
    bus.subscribe("evt", lambda: results.append("c"))
    bus.publish("evt")
    assert results == ["a", "b", "c"]
