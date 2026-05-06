"""EventBus — publish-subscribe decoupling for framework→module notifications.

Publisher calls publish() which submits events to a background event loop
and returns immediately. The background loop dispatches to all subscribers.
"""

import asyncio
import inspect
import logging
import threading

logger = logging.getLogger("polaris.events")


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[callable]] = {}
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def subscribe(self, event: str, handler: callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def publish(self, event: str, _after: str | None = None, **payload) -> None:
        """发布事件。_after 指定所有 handler 执行完后自动发布的后续事件名。"""
        handlers = self._handlers.get(event, [])
        if not handlers and not _after:
            return
        self._loop.call_soon_threadsafe(
            self._dispatch, event, handlers, payload, _after
        )

    def _dispatch(self, event: str, handlers: list, payload: dict,
                  after: str | None) -> None:
        for h in handlers:
            try:
                result = h(**payload)
                if inspect.isawaitable(result):
                    self._loop.create_task(result)
            except Exception:
                logger.exception(f"事件处理失败: {event} -> {h}")
        if after:
            self.publish(after, **payload)


event_bus = EventBus()
