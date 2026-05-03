"""ReminderService — facade encapsulating reminder store + scheduler operations.

Calendar tools (and other callers) use this service instead of directly
importing ReminderStore, Reminder models, or accessing the global scheduler.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from .models import Reminder, RepeatRule, ReminderStatus

logger = logging.getLogger("polaris.reminders.service")


class ReminderService:
    """High-level API for event-related reminder operations.

    Wraps ReminderStore persistence and ReminderScheduler scheduling into
    single-method calls used by calendar tools.
    """

    def __init__(self, store, scheduler):
        self._store = store
        self._scheduler = scheduler

    def create_event_reminder(
        self,
        event_title: str,
        event_time_str: str,
        event_id: str,
        channel: str,
        session_id: str,
    ) -> Optional[str]:
        """Create a reminder that fires 15 minutes before the event.

        Returns the new reminder_id, or None if the reminder time is already
        in the past (or on error).
        """
        try:
            event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            reminder_time = event_datetime - timedelta(minutes=15)

            is_past = reminder_time <= datetime.now()
            status = ReminderStatus.CANCELLED if is_past else ReminderStatus.ACTIVE

            reminder = Reminder(
                title=f"{event_title} 即将开始",
                description=f"日程「{event_title}」将在15分钟后开始",
                trigger_time=reminder_time,
                repeat_rule=RepeatRule.NONE,
                event_id=event_id,
                channel=channel or "admin",
                session_id=session_id or "",
                status=status,
            )
            self._store.create(reminder)

            # Only schedule future reminders
            if not is_past and self._scheduler:
                self._scheduler.add_reminder(reminder)

            logger.info(
                f"已创建日程关联提醒: {reminder.id} @ {reminder_time} (past={is_past})"
            )
            return reminder.id
        except Exception as e:
            logger.error(f"创建日程关联提醒失败: {e}")
            return None

    def update_event_reminder(self, event: dict, date: str, updates: dict) -> None:
        """Update the trigger time of an event's reminder.

        Only takes effect when ``time`` or ``date`` is in *updates*.
        If the new trigger time is in the future the reminder is re-activated.
        """
        reminder_id = event.get("reminder_id")
        if not reminder_id:
            return

        if "time" not in updates and "date" not in updates:
            logger.info("时间/日期没有变化，跳过更新提醒")
            return

        try:
            reminder = self._store.get(reminder_id)
            if not reminder:
                logger.warning(f"提醒不存在: {reminder_id}")
                return

            event_time = event.get("time", "09:00")
            event_datetime = datetime.strptime(f"{date} {event_time}", "%Y-%m-%d %H:%M")
            new_reminder_time = event_datetime - timedelta(minutes=15)

            new_title = f"{event['title']} 即将开始"
            self._store.update(
                reminder_id, trigger_time=new_reminder_time, title=new_title
            )

            # Re-read after update to get fresh state
            reminder = self._store.get(reminder_id)

            if new_reminder_time > datetime.now():
                self._store.update(reminder_id, status=ReminderStatus.ACTIVE)
                reminder = self._store.get(reminder_id)

            # Reschedule in scheduler
            if self._scheduler:
                self._scheduler.remove_reminder(reminder_id)
                if new_reminder_time > datetime.now():
                    self._scheduler.add_reminder(reminder)

            logger.info(f"已更新日程关联提醒: {reminder_id} @ {new_reminder_time}")
        except Exception as e:
            logger.error(f"更新日程关联提醒失败: {e}")

    def delete_event_reminder(self, event: dict) -> None:
        """Delete the reminder associated with an event."""
        reminder_id = event.get("reminder_id")
        if not reminder_id:
            return

        try:
            if self._store.delete(reminder_id):
                if self._scheduler:
                    self._scheduler.remove_reminder(reminder_id)
                logger.info(f"已删除日程关联提醒: {reminder_id}")
        except Exception as e:
            logger.error(f"删除日程关联提醒失败: {e}")
