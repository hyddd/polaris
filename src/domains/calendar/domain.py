"""CalendarDomain — 日程管理核心服务。"""

import logging
import uuid

from src.core.events import event_bus
from .models import CalendarEvent
from .store import CalendarStore

logger = logging.getLogger("polaris.calendar")

# 键名规范化映射：LLM 可能传 "new_time" 而非 "time"
_KEY_MAP = {"new_time": "time", "new_date": "date", "new_title": "title", "new_duration": "duration"}


class CalendarDomain:
    def __init__(self, store: CalendarStore):
        self._store = store

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_events(self, date: str | None = None) -> list[CalendarEvent]:
        """按日期列日程，date=None 返回全部。"""
        return self._store.list_events(date=date)

    def get_event(self, event_id: str) -> CalendarEvent | None:
        """按 ID 获取事件。"""
        return self._store.get_event(event_id)

    def search(self, keyword: str) -> list[tuple[str, CalendarEvent]]:
        """关键词模糊匹配标题。"""
        return self._store.search(keyword)

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def create_event(self, date: str, title: str, time: str = "09:00",
                     duration: int = 60, attendees: list | None = None,
                     channel: str = "admin", session_id: str = "") -> CalendarEvent:
        """创建日程事件。"""
        event = CalendarEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            title=title,
            time=time,
            duration=duration,
            attendees=attendees or [],
            date=date,
        )
        self._store.create_event(date, event)
        event_time_str = f"{date} {event.time}"
        event_bus.publish("calendar:event_created",
                          event_id=event.id, title=event.title,
                          event_time_str=event_time_str,
                          channel=channel, session_id=session_id)
        return event

    def update_event(self, event_id: str, updates: dict,
                     date: str | None = None) -> CalendarEvent | None:
        """更新事件，支持键名规范化和跨日期移动。"""
        # 键名规范化
        updates = {_KEY_MAP.get(k, k): v for k, v in updates.items()}

        new_date = updates.pop("date", None) or date
        result = self._store.update_event(event_id, updates, new_date=new_date)
        if result:
            event_time_str = f"{result.date} {result.time}"
            event_bus.publish("calendar:event_updated",
                              event_id=result.id, title=result.title,
                              event_time_str=event_time_str)
        return result

    def delete_event(self, event_id: str) -> bool:
        """删除事件。"""
        deleted = self._store.delete_event(event_id)
        if deleted:
            event_bus.publish("calendar:event_deleted", event_id=event_id)
        return deleted

    # ------------------------------------------------------------------
    # 维护
    # ------------------------------------------------------------------

    def cleanup(self, retention_days: int = 14) -> int:
        """清理过期日程，返回清理数量。"""
        return self._store.cleanup(retention_days)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: CalendarDomain | None = None


def get_calendar_domain() -> CalendarDomain:
    return _domain


def set_calendar_domain(domain: CalendarDomain | None):
    global _domain
    _domain = domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(**kwargs):
    from src.core.config import config
    path = str(config.resolve_path(
        config.get("storage.calendar_file", "data/calendar.json")))
    store = CalendarStore(path)
    global _domain
    _domain = CalendarDomain(store)
    logger.info("日程域已初始化")


event_bus.subscribe("app:startup", _on_startup)


# ---------------------------------------------------------------------------
# Cleanup 集成
# ---------------------------------------------------------------------------
def _on_cleanup(**kwargs):
    domain = get_calendar_domain()
    if domain:
        count = domain.cleanup()
        if count:
            logger.info(f"清理 {count} 条过期日程")


event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
