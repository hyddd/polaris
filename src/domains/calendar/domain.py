"""CalendarDomain — 日程管理核心服务。"""

import logging
import uuid

from src.core.infra import event_bus
from .models import CalendarEvent
from .store import CalendarStore

logger = logging.getLogger("polaris.calendar")

# 键名规范化映射：LLM 可能传 "new_time" 而非 "time"
_KEY_MAP = {"new_time": "time", "new_date": "date", "new_title": "title", "new_duration": "duration"}


class CalendarDomain:
    def __init__(self, store: CalendarStore):
        self._store = store

    @property
    def public_error(self) -> str | None:
        """最近一次读公共库失败的原因（列表里只剩私有数据时用来提示）。"""
        return getattr(self._store, "public_error", None)

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
                     channel: str = "admin", session_id: str = "",
                     scope: str | None = None) -> CalendarEvent:
        """创建日程事件。scope：public 存公共库、private 存本机；不传用默认。"""
        from src.core.db import resolve_scope
        scope = resolve_scope(scope)
        event = CalendarEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            title=title,
            time=time,
            duration=duration,
            attendees=attendees or [],
            date=date,
            scope=scope,
        )
        # personal 存公共日程时 ID 由 team 服务分配，以存储返回的为准
        event = self._store.create_event(date, event)
        event_time_str = f"{date} {event.time}"
        # 关联提醒跟随日程的 scope：公共日程的提醒也是公共的（由 team 服务创建，见 reminder 域）
        event_bus.publish("calendar:event_created",
                          event_id=event.id, title=event.title,
                          event_time_str=event_time_str,
                          channel=channel, session_id=session_id, scope=scope)
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
                              event_time_str=event_time_str, scope=result.scope)
        return result

    def delete_event(self, event_id: str) -> bool:
        """删除事件。"""
        existing = self._store.get_event(event_id)
        deleted = self._store.delete_event(event_id)
        if deleted:
            event_bus.publish("calendar:event_deleted", event_id=event_id,
                              scope=existing.scope if existing else None)
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
    from src.core.db import is_team, public_enabled, instance_info
    from src.core.db.public_store import NoPrivate
    from .public_store import PublicCalendarStore, RemoteCalendarStore, ScopedCalendarStore
    if is_team():
        store = ScopedCalendarStore(NoPrivate(), PublicCalendarStore() if public_enabled() else None)
    else:
        path = str(config.resolve_path(config.get("storage.calendar_file", "data/calendar.json")))
        store = ScopedCalendarStore(CalendarStore(path), RemoteCalendarStore() if public_enabled() else None)
    global _domain
    _domain = CalendarDomain(store)
    logger.info(f"日程域已初始化（{instance_info()['mode_label']}，公共数据{'可用' if public_enabled() else '未启用'}）")


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
