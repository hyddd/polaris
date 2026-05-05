"""CalendarStore — 日程事件 JSON 文件持久化。"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from src.core.storage.store import JsonFileStore
from .models import CalendarEvent

logger = logging.getLogger("polaris.calendar.store")


class CalendarStore:
    """日程事件持久化存储，数据格式与现有 data/calendar.json 兼容。"""

    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._store = JsonFileStore(file_path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 底层读写
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        """读取原始 JSON 数据，文件不存在或为空返回空列表。"""
        if self._path.exists():
            text = self._path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            raw = json.loads(text)
            return raw if isinstance(raw, list) else []
        return []

    def _save(self, data: list[dict]) -> None:
        """原子写入 JSON 文件。"""
        self._store.save(data)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_events(self, date: str | None = None) -> list[CalendarEvent]:
        """按日期筛选或返回全部事件。"""
        data = self._load()
        result = []
        for day in data:
            d = day.get("date", "")
            if date and d != date:
                continue
            for ev in day.get("events", []):
                result.append(CalendarEvent.from_dict(ev, date=d))
        return result

    def get_event(self, event_id: str) -> CalendarEvent | None:
        """按 ID 获取单个事件。"""
        data = self._load()
        for day in data:
            for ev in day.get("events", []):
                if ev.get("id") == event_id:
                    return CalendarEvent.from_dict(ev, date=day.get("date", ""))
        return None

    def search(self, keyword: str) -> list[tuple[str, CalendarEvent]]:
        """关键词模糊匹配标题，返回 (date, event) 对。"""
        data = self._load()
        matches = []
        kw = keyword.lower()
        for day in data:
            d = day.get("date", "")
            for ev in day.get("events", []):
                if kw in ev.get("title", "").lower():
                    matches.append((d, CalendarEvent.from_dict(ev, date=d)))
        return matches

    # ------------------------------------------------------------------
    # 写操作（需要锁保护）
    # ------------------------------------------------------------------

    def create_event(self, date: str, event: CalendarEvent) -> CalendarEvent:
        """在指定日期下创建事件。"""
        with self._lock:
            data = self._load()
            ev_dict = event.to_dict()
            for day in data:
                if day.get("date") == date:
                    day.setdefault("events", []).append(ev_dict)
                    self._save(data)
                    logger.info(f"已创建日程: {date} {event.time} {event.title}")
                    return event
            data.append({"date": date, "events": [ev_dict]})
            self._save(data)
            logger.info(f"已创建日程: {date} {event.time} {event.title}")
            return event

    def update_event(self, event_id: str, updates: dict,
                     new_date: str | None = None) -> CalendarEvent | None:
        """更新事件，支持跨日期移动。

        Args:
            event_id: 事件 ID。
            updates: 要更新的字段（不包含 date）。
            new_date: 若非 None，将事件移到新日期。

        Returns:
            更新后的 CalendarEvent，未找到返回 None。
        """
        with self._lock:
            data = self._load()
            for day in data:
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    if ev.get("id") == event_id:
                        # 应用更新（排除 date 键，date 由 new_date 控制）
                        ev.update({k: v for k, v in updates.items() if k != "date"})

                        if new_date and new_date != day.get("date"):
                            # 跨日期移动：从原日期移除，插入新日期
                            events.pop(i)
                            moved = False
                            for d in data:
                                if d.get("date") == new_date:
                                    d.setdefault("events", []).append(ev)
                                    moved = True
                                    break
                            if not moved:
                                data.append({"date": new_date, "events": [ev]})

                        self._save(data)
                        result_date = new_date or day.get("date", "")
                        result = CalendarEvent.from_dict(ev, date=result_date)
                        logger.info(f"已更新日程: {event_id}")
                        return result
            return None

    def delete_event(self, event_id: str) -> bool:
        """删除事件。"""
        with self._lock:
            data = self._load()
            for day in data:
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    if ev.get("id") == event_id:
                        events.pop(i)
                        self._save(data)
                        logger.info(f"已删除日程: {event_id}")
                        return True
            return False

    def cleanup(self, retention_days: int = 14) -> int:
        """清理过期日程，返回清理数量。"""
        with self._lock:
            data = self._load()
            cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
            kept = [day for day in data if day.get("date", "") >= cutoff]
            archived = len(data) - len(kept)
            if archived:
                self._save(kept)
                logger.info(f"清理 {archived} 条过期日程（保留 {retention_days} 天）")
            return archived
