import threading
import time
from collections import defaultdict
from contextlib import contextmanager


class Metrics:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._counters = defaultdict(int)
                    cls._instance._timers = defaultdict(list)
        return cls._instance

    def inc(self, name: str, value: int = 1):
        self._counters[name] += value

    @contextmanager
    def timer(self, name: str):
        start = time.monotonic()
        yield
        elapsed = time.monotonic() - start
        self._timers[name].append(elapsed)

    def snapshot(self) -> dict:
        return {
            "counters": dict(self._counters),
            "timers": {
                k: {"avg_ms": round(sum(v) / len(v) * 1000, 1), "count": len(v)}
                for k, v in self._timers.items()
            },
        }

    def reset(self):
        self._counters.clear()
        self._timers.clear()


metrics = Metrics()
