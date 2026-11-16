"""日程的公共存储和公私组合存储。规则同待办：PublicCalendarStore（team，MySQL）、
RemoteCalendarStore（personal → team 的 HTTP 接口）、ScopedCalendarStore（创建按 scope 分流，读取合并，按 ID 路由）。"""
import logging
from datetime import timedelta

from src.core.db import PUBLIC, PRIVATE
from src.core.db.public_store import PublicStoreBase, MergedReadMixin, dump_list, load_list, date_str, now
from src.core.db.remote import RemoteError, get_remote
from .models import CalendarEvent
from .store import CalendarStore

logger = logging.getLogger("polaris.calendar.public")

_COLUMNS = {"title": "title", "time": "start_time", "duration": "duration_min", "attendees": "attendees"}


class RemoteCalendarStore:
    """personal → team：公共日程通过 /api/data/calendar 读写。"""

    def __init__(self, client_getter=get_remote):
        self._client_getter = client_getter

    def _c(self):
        c = self._client_getter()
        if c is None:
            raise RemoteError("没有连接团队服务")
        return c

    def _item(self, d: dict) -> CalendarEvent:
        return CalendarEvent.from_dict({**d, "scope": PUBLIC})

    def _all(self) -> list[CalendarEvent]:
        return [self._item(d) for d in self._c().get("/api/data/calendar").get("items", [])]

    def list_events(self, date: str | None = None) -> list[CalendarEvent]:
        events = self._all()
        return [e for e in events if e.date == date] if date else events

    def get_event(self, event_id: str) -> CalendarEvent | None:
        return next((e for e in self._all() if e.id == event_id), None)

    def search(self, keyword: str) -> list[tuple[str, CalendarEvent]]:
        kw = keyword.lower()
        return [(e.date, e) for e in self._all() if kw in e.title.lower()]

    def create_event(self, date: str, event: CalendarEvent) -> CalendarEvent:
        body = {"date": date, "title": event.title, "time": event.time, "duration": event.duration,
                "attendees": event.attendees, "scope": PUBLIC}
        return self._item(self._c().post("/api/data/calendar", {"data": body})["item"])

    def update_event(self, event_id: str, updates: dict, new_date: str | None = None) -> CalendarEvent | None:
        body = dict(updates)
        if new_date:
            body["date"] = new_date
        try:
            r = self._c().put(f"/api/data/calendar/{event_id}", {"data": body})
        except RemoteError as e:
            if e.status == 404:
                return None
            raise
        return self._item(r["item"]) if r.get("item") else self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        try:
            self._c().delete(f"/api/data/calendar/{event_id}")
            return True
        except RemoteError as e:
            if e.status == 404:
                return False
            raise


def _time_str(value) -> str:
    """MySQL TIME 在 PyMySQL 里是 timedelta。"""
    if isinstance(value, timedelta):
        minutes = int(value.total_seconds()) // 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return str(value)[:5] if value else "09:00"


class PublicCalendarStore(PublicStoreBase):

    def _row(self, r: dict) -> CalendarEvent:
        return CalendarEvent(id=r["id"], title=r["title"], time=_time_str(r["start_time"]),
                             duration=int(r["duration_min"]), attendees=load_list(r["attendees"]),
                             date=date_str(r["event_date"]), scope=PUBLIC)

    def list_events(self, date: str | None = None) -> list[CalendarEvent]:
        db = self.db()
        sql, args = f"SELECT * FROM {db.t('calendar_events')}", ()
        if date:
            sql, args = sql + " WHERE event_date=%s", (date,)
        return [self._row(r) for r in db.fetchall(sql + " ORDER BY event_date, start_time", args)]

    def get_event(self, event_id: str) -> CalendarEvent | None:
        db = self.db()
        r = db.fetchone(f"SELECT * FROM {db.t('calendar_events')} WHERE id=%s", (event_id,))
        return self._row(r) if r else None

    def search(self, keyword: str) -> list[tuple[str, CalendarEvent]]:
        db = self.db()
        rows = db.fetchall(f"SELECT * FROM {db.t('calendar_events')} WHERE title LIKE %s "
                           f"ORDER BY event_date, start_time", (f"%{keyword}%",))
        return [(e.date, e) for e in map(self._row, rows)]

    def create_event(self, date: str, event: CalendarEvent) -> CalendarEvent:
        db = self.db()
        ts = now()
        db.execute(f"INSERT INTO {db.t('calendar_events')} "
                   f"(id, title, event_date, start_time, duration_min, attendees, created_at, updated_at) "
                   f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                   (event.id, event.title, date, event.time, event.duration, dump_list(event.attendees), ts, ts))
        event.date, event.scope = date, PUBLIC
        logger.info(f"已创建公共日程: {date} {event.time} {event.title}")
        return event

    def update_event(self, event_id: str, updates: dict, new_date: str | None = None) -> CalendarEvent | None:
        db = self.db()
        sets, args = [], []
        for k, v in updates.items():
            if k not in _COLUMNS:
                continue
            sets.append(f"{_COLUMNS[k]}=%s")
            args.append(dump_list(v) if k == "attendees" else v)
        if new_date:
            sets.append("event_date=%s")
            args.append(new_date)
        if sets:
            sets.append("updated_at=%s")
            args += [now(), event_id]
            db.execute(f"UPDATE {db.t('calendar_events')} SET {', '.join(sets)} WHERE id=%s", args)
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        db = self.db()
        return db.execute(f"DELETE FROM {db.t('calendar_events')} WHERE id=%s", (event_id,)) > 0


class ScopedCalendarStore(MergedReadMixin):
    def __init__(self, private: CalendarStore, public: PublicCalendarStore | None):
        self._private = private
        self._public = public

    def list_events(self, date: str | None = None) -> list[CalendarEvent]:
        events = self._private.list_events(date) + self._public_read(lambda: self._public.list_events(date), [])
        return sorted(events, key=lambda e: (e.date, e.time))

    def get_event(self, event_id: str) -> CalendarEvent | None:
        return self._private.get_event(event_id) or self._public_read(lambda: self._public.get_event(event_id), None)

    def search(self, keyword: str) -> list[tuple[str, CalendarEvent]]:
        return self._private.search(keyword) + self._public_read(lambda: self._public.search(keyword), [])

    def _owner(self, event_id: str):
        if self._private.get_event(event_id):
            return self._private
        if self._public is not None and self._public.get_event(event_id):
            return self._public
        return None

    def create_event(self, date: str, event: CalendarEvent) -> CalendarEvent:
        if event.scope == PUBLIC:
            if self._public is None:
                raise RuntimeError("公共库未启用，不能创建公共日程")
            return self._public.create_event(date, event)
        event.scope = PRIVATE
        return self._private.create_event(date, event)

    def update_event(self, event_id: str, updates: dict, new_date: str | None = None) -> CalendarEvent | None:
        owner = self._owner(event_id)
        return owner.update_event(event_id, updates, new_date=new_date) if owner else None

    def delete_event(self, event_id: str) -> bool:
        owner = self._owner(event_id)
        return owner.delete_event(event_id) if owner else False

    def cleanup(self, retention_days: int = 14) -> int:
        return self._private.cleanup(retention_days)   # 公共数据不由个人实例清理
