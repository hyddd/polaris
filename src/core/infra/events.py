"""EventBus — publish-subscribe decoupling for framework→module notifications."""

import logging

logger = logging.getLogger("polaris.events")


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[callable]] = {}

    def subscribe(self, event: str, handler: callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def publish(self, event: str, **payload) -> None:
        for h in self._handlers.get(event, []):
            try:
                h(**payload)
            except Exception:
                logger.exception(f"事件处理失败: {event} -> {h}")


event_bus = EventBus()
