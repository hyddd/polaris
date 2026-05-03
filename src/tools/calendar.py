import os
import uuid
import logging
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("polaris.tools.calendar")


def create_default() -> "GoogleCalendarTool":
    """Factory for auto-discovery. Creates a GoogleCalendarTool with default config."""
    from src.config import CALENDAR_FILE
    return GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True)


class CalendarInput(BaseModel):
    action: Literal["list", "search", "create", "update", "delete"] = Field(
        description="操作类型：list=查看日程, search=搜索事件, create=创建, update=修改, delete=删除"
    )
    date: Optional[str] = Field(default=None, description="list/create/update/delete 时的日期，格式 YYYY-MM-DD")
    keyword: Optional[str] = Field(default=None, description="search 时的搜索关键词")
    title: Optional[str] = Field(default=None, description="create/update/delete 时的事件标题（用于匹配）")
    time: Optional[str] = Field(default=None, description="create/update 时的事件时间，格式 HH:MM")
    attendees: Optional[list[str]] = Field(default=None, description="create 时的参与者列表")
    duration: Optional[int] = Field(default=60, description="create 时的事件时长（分钟），默认 60")
    event_id: Optional[str] = Field(default=None, description="update 或 delete 时的事件 ID（优先级高于 title+date）")
    updates: Optional[dict | str] = Field(default=None, description='update 时要修改的字段，key 可选: time(格式HH:MM), date(格式YYYY-MM-DD), title, duration. 示例: {"time":"15:00"}')


class GoogleCalendarTool(BaseTool):
    name: str = "calendar"
    description: str = """管理日历事件。

规则：
1. 修改日程必须用 update，禁止 delete + create
2. 删除/修改前必须先 search 获取 event_id
3. 用户说"推迟""改到""换个时间""取消"等，都是修改意图，用 update

示例流程：
- "把明天晨会改到下午3点" → search(keyword="晨会") → update(event_id="xxx", updates={"time":"15:00"})
- "推迟会议1小时" → search(keyword="会议") → update(event_id="xxx", updates={"time":"原时间+1h"})"""
    args_schema: type[BaseModel] = CalendarInput
    data_file: str = ""
    use_mock: bool = os.getenv("CALENDAR_USE_MOCK", "false").lower() == "true"

    def _run(self, action: str, date: str | None = None, keyword: str | None = None,
             title: str | None = None, time: str | None = None, attendees: list[str] | None = None,
             duration: int = 60, event_id: str | None = None, updates: dict | None = None) -> str:
        from src.data_layer.loader import load_json, save_json

        path = Path(self.data_file)
        raw = load_json(path)
        data = raw if isinstance(raw, list) else []

        if action == "list":
            if not date:
                return "请提供要查询的日期（YYYY-MM-DD）。"
            for day in data:
                if day.get("date") == date:
                    events = day.get("events", [])
                    if not events:
                        return f"{date} 没有日程安排。"
                    return "\n".join(
                        f"- [{ev['id']}] {ev['time']} {ev['title']} ({ev.get('duration', 60)}分钟)"
                        for ev in sorted(events, key=lambda e: e.get("time", ""))
                    )
            return f"{date} 没有日程安排。"

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            matches = []
            for day in data:
                for ev in day.get("events", []):
                    if keyword.lower() in ev.get("title", "").lower():
                        matches.append((day["date"], ev))
            if not matches:
                return f"没有找到包含「{keyword}」的日程。"
            return "\n".join(f"- [{ev['id']}] {date} {ev['time']} {ev['title']}" for date, ev in matches)

        elif action == "create":
            if not title or not date:
                return "创建日程需要提供标题和日期。"
            new_event = {
                "id": f"evt-{uuid.uuid4().hex[:8]}",
                "title": title,
                "time": time or "09:00",
                "duration": duration,
                "attendees": attendees or [],
                "reminder_id": None,
            }
            for day in data:
                if day.get("date") == date:
                    day.setdefault("events", []).append(new_event)
                    save_json(path, data)
                    # 创建关联提醒
                    self._create_event_reminder(new_event, date)
                    return f"已添加日程：{date} {new_event['time']} {title}"
            data.append({"date": date, "events": [new_event]})
            save_json(path, data)
            # 创建关联提醒
            self._create_event_reminder(new_event, date)
            return f"已添加日程：{date} {new_event['time']} {title}"

        elif action == "update":
            # Fallback: if updates dict not provided, build it from individual fields
            # This handles models that struggle with dict parameters
            if not updates:
                updates = {}
                if time:
                    updates["time"] = time
                # Note: title param is used for matching, not for updating
                if not updates:
                    return "修改日程需要提供要修改的字段。请在 updates 中指定要修改的内容，例如 {\"time\": \"15:00\"}"

            # Defensive: some models pass updates as a JSON string instead of dict
            if isinstance(updates, str):
                import json as _json
                try:
                    updates = _json.loads(updates)
                except _json.JSONDecodeError:
                    return "修改日程需要提供要修改的字段（JSON 对象），收到的却是字符串。"

            # Normalize update keys: LLM may pass "new_time" instead of "time", "new_date" instead of "date"
            _key_map = {"new_time": "time", "new_date": "date", "new_title": "title", "new_duration": "duration"}
            updates = {_key_map.get(k, k): v for k, v in updates.items()}

            new_date = updates.get("date")
            # Find by event_id or title (with optional date filter)
            for day in data:
                if date and day.get("date") != date:
                    continue
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    matched = False
                    if event_id and ev["id"] == event_id:
                        matched = True
                    elif title and title.lower() in ev.get("title", "").lower():
                        matched = True
                    if matched:
                        if new_date and new_date != day.get("date"):
                            # Date changed: move event to new date
                            events.pop(i)
                            ev.update({k: v for k, v in updates.items() if k != "date"})
                            moved = False
                            for d in data:
                                if d.get("date") == new_date:
                                    d.setdefault("events", []).append(ev)
                                    moved = True
                                    break
                            if not moved:
                                data.append({"date": new_date, "events": [ev]})
                        else:
                            # Same date update — filter out "date" key to avoid corrupting event
                            ev.update({k: v for k, v in updates.items() if k != "date"})
                        save_json(path, data)
                        # 更新关联提醒
                        self._update_event_reminder(ev, new_date or day.get("date"), updates)
                        return f"已更新日程：{ev.get('title', event_id)}"
            return f"未找到日程：{event_id or f'{date} {title}'}"

        elif action == "delete":
            # Find by event_id or title (with optional date filter)
            for day in data:
                if date and day.get("date") != date:
                    continue
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    matched = False
                    if event_id and ev["id"] == event_id:
                        matched = True
                    elif title and title.lower() in ev.get("title", "").lower():
                        matched = True
                    if matched:
                        matched_title = ev["title"]
                        # 删除关联提醒
                        self._delete_event_reminder(ev)
                        events.pop(i)
                        save_json(path, data)
                        return f"已删除日程：{matched_title}"
            return f"未找到日程：{event_id or f'{date} {title}'}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)

    def _create_event_reminder(self, event: dict, date: str):
        """为日程创建关联提醒（提前15分钟）"""
        from src.reminders.models import Reminder, RepeatRule
        from src.reminders.store import ReminderStore
        from src.config import REMINDERS_FILE
        from src.context import get_channel, get_session_id

        try:
            event_datetime = datetime.strptime(f"{date} {event.get('time', '09:00')}", "%Y-%m-%d %H:%M")
            reminder_time = event_datetime - timedelta(minutes=15)

            # 只创建未来的提醒
            if reminder_time <= datetime.now():
                return

            # 从 context 获取 channel 和 session_id
            channel = get_channel()
            session_id = get_session_id()

            # 从日程数据中获取 channel（如果保存了的话）
            if not channel:
                channel = event.get("channel", "admin")
            if not session_id:
                session_id = event.get("session_id", "")

            reminder = Reminder(
                title=f"{event['title']} 即将开始",
                description=f"日程「{event['title']}」将在15分钟后开始",
                trigger_time=reminder_time,
                repeat_rule=RepeatRule.NONE,
                event_id=event["id"],
                channel=channel or "admin",
                session_id=session_id or "",
            )
            store = ReminderStore(str(REMINDERS_FILE))
            store.create(reminder)

            # 添加到调度器
            from src.reminders import get_scheduler
            scheduler = get_scheduler()
            if scheduler:
                scheduler.add_reminder(reminder)

            # 保存提醒ID和channel到日程
            event["reminder_id"] = reminder.id
            event["reminder_channel"] = channel
            event["reminder_session_id"] = session_id
            logger.info(f"已创建日程关联提醒: {reminder.id} @ {reminder_time}")
        except Exception as e:
            logger.error(f"创建日程关联提醒失败: {e}")

    def _update_event_reminder(self, event: dict, date: str, updates: dict):
        """更新日程关联提醒的时间"""
        from src.reminders.store import ReminderStore
        from src.reminders.models import ReminderStatus
        from src.config import REMINDERS_FILE

        reminder_id = event.get("reminder_id")
        if not reminder_id:
            return

        # 只在时间或日期变化时更新
        if "time" not in updates and "date" not in updates:
            return

        try:
            store = ReminderStore(str(REMINDERS_FILE))
            reminder = store.get(reminder_id)
            if not reminder:
                return

            event_datetime = datetime.strptime(f"{date} {event.get('time', '09:00')}", "%Y-%m-%d %H:%M")
            new_reminder_time = event_datetime - timedelta(minutes=15)

            # 更新提醒时间和标题
            new_title = f"{event['title']} 即将开始"
            store.update(reminder_id, trigger_time=new_reminder_time, title=new_title)

            # 重新获取更新后的 reminder 对象
            reminder = store.get(reminder_id)

            # 更新调度器
            from src.reminders import get_scheduler
            scheduler = get_scheduler()
            if scheduler:
                scheduler.remove_reminder(reminder_id)
                if new_reminder_time > datetime.now() and reminder.status == ReminderStatus.ACTIVE:
                    scheduler.add_reminder(reminder)

            logger.info(f"已更新日程关联提醒: {reminder_id} @ {new_reminder_time}")
        except Exception as e:
            logger.error(f"更新日程关联提醒失败: {e}")

    def _delete_event_reminder(self, event: dict):
        """删除日程关联提醒"""
        from src.reminders.store import ReminderStore
        from src.config import REMINDERS_FILE

        reminder_id = event.get("reminder_id")
        if not reminder_id:
            return

        try:
            store = ReminderStore(str(REMINDERS_FILE))
            if store.delete(reminder_id):
                from src.reminders import get_scheduler
                scheduler = get_scheduler()
                if scheduler:
                    scheduler.remove_reminder(reminder_id)
                logger.info(f"已删除日程关联提醒: {reminder_id}")
        except Exception as e:
            logger.error(f"删除日程关联提醒失败: {e}")
