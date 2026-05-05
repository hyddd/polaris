"""Tests for src.core.metrics — lightweight in-process metrics."""

import time
from src.core.observability.metrics import Metrics


def test_inc():
    m = Metrics()
    m.reset()
    m.inc("foo")
    m.inc("foo")
    m.inc("bar", 3)
    assert m._counters["foo"] == 2
    assert m._counters["bar"] == 3


def test_timer():
    m = Metrics()
    m.reset()
    with m.timer("t"):
        time.sleep(0.01)
    assert len(m._timers["t"]) == 1
    assert m._timers["t"][0] >= 0.01


def test_snapshot():
    m = Metrics()
    m.reset()
    m.inc("c1")
    m.inc("c1")
    m.inc("c2")
    with m.timer("t1"):
        pass
    snap = m.snapshot()
    assert snap["counters"] == {"c1": 2, "c2": 1}
    assert "t1" in snap["timers"]
    assert snap["timers"]["t1"]["count"] == 1
    assert isinstance(snap["timers"]["t1"]["avg_ms"], float)


def test_reset():
    m = Metrics()
    m.inc("x")
    with m.timer("y"):
        pass
    m.reset()
    assert m._counters == {}
    assert m._timers == {}
    snap = m.snapshot()
    assert snap == {"counters": {}, "timers": {}}
