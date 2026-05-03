"""ReminderService — facade encapsulating reminder store + cron scheduler operations.

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

    Wraps ReminderStore persistence and CronScheduler scheduling into
    single-method calls used by calendar tools.
    """

    def __init__(self, store, cron_scheduler, handler):
        self._store = store
        self._scheduler = cron_scheduler
        self._handler = handler

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
                self._scheduler.add_date_job(
                    self._handler.handle, reminder.trigger_time, reminder.id, args=[reminder]
                )

            logger.info(
                f"已创建日程关联提醒: {reminder.id} @ {reminder_time} (past={is_past})"
            )
            return reminder.id
        except Exception as e:
            logger.error(f"创建日程关联提醒失败: {e}")
            return None

    def update_event_reminder(self, event_id: str, title: str, event_time_str: str) -> None:
        """Update the trigger time of an event's reminder after calendar change."""
        for reminder in self._store.find_by_event_id(event_id):
            try:
                event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                new_reminder_time = event_datetime - timedelta(minutes=15)
                new_title = f"{title} 即将开始"

                self._store.update(reminder.id, trigger_time=new_reminder_time, title=new_title)

                if new_reminder_time > datetime.now():
                    # 日程推迟到未来 → 重新激活已触发的提醒
                    self._store.update(reminder.id, status=ReminderStatus.ACTIVE)

                reminder = self._store.get(reminder.id)

                if self._scheduler:
                    self._scheduler.remove_job(reminder.id)
                    if new_reminder_time > datetime.now():
                        self._scheduler.add_date_job(
                            self._handler.handle, new_reminder_time, reminder.id, args=[reminder]
                        )

                logger.info(f"已更新日程关联提醒: {reminder.id} @ {new_reminder_time}")
            except Exception as e:
                logger.error(f"更新日程关联提醒失败: {e}")

    def delete_event_reminder(self, event_id: str) -> None:
        """Delete the reminder associated with an event."""
        for reminder in self._store.find_by_event_id(event_id):
            try:
                if self._store.delete(reminder.id):
                    if self._scheduler:
                        self._scheduler.remove_job(reminder.id)
                    logger.info(f"已删除日程关联提醒: {reminder.id}")
            except Exception as e:
                logger.error(f"删除日程关联提醒失败: {e}")

# ── Scheduling helpers used by tool.py and setup.py ──────────────

def schedule_reminder(cron, handler, reminder: Reminder):
    """根据提醒的重复规则调度到 cron 中。"""
    if reminder.repeat_rule == RepeatRule.NONE:
        now = datetime.now()
        if reminder.trigger_time <= now:
            logger.info(f"提醒时间已过，立即触发: {reminder.id} - {reminder.title}")
            handler.handle(reminder)
        else:
            cron.add_date_job(handler.handle, reminder.trigger_time, reminder.id, args=[reminder])
    else:
        kwargs = repeat_rule_to_cron_kwargs(reminder.trigger_time, reminder.repeat_rule)
        cron.add_cron_job(handler.handle, reminder.id, **kwargs)


def repeat_rule_to_cron_kwargs(trigger_time, repeat_rule):
    """将重复规则转换为 APScheduler CronTrigger 关键字参数。"""
    if repeat_rule == RepeatRule.DAILY:
        return {"hour": trigger_time.hour, "minute": trigger_time.minute}
    elif repeat_rule == RepeatRule.WEEKLY:
        return {
            "hour": trigger_time.hour,
            "minute": trigger_time.minute,
            "day_of_week": trigger_time.weekday(),
        }
    elif repeat_rule == RepeatRule.MONTHLY:
        return {
            "hour": trigger_time.hour,
            "minute": trigger_time.minute,
            "day": trigger_time.day,
        }
    return {}
