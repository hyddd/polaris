import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from .models import Reminder, RepeatRule

logger = logging.getLogger("polaris.reminders.scheduler")


class ReminderScheduler:
    def __init__(self, store, handler):
        self.scheduler = AsyncIOScheduler()
        self.store = store
        self.handler = handler

    def start(self):
        """启动调度器，加载所有活跃提醒"""
        reminders = self.store.list_active()
        for reminder in reminders:
            self._add_job(reminder)
        self.scheduler.start()
        logger.info(f"提醒调度器已启动，加载 {len(reminders)} 个提醒")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()

    def add_reminder(self, reminder: Reminder):
        """添加提醒到调度器"""
        self._add_job(reminder)

    def remove_reminder(self, reminder_id: str):
        """从调度器移除提醒"""
        try:
            self.scheduler.remove_job(reminder_id)
        except Exception:
            pass

    def _add_job(self, reminder: Reminder):
        """添加提醒任务"""
        now = datetime.now()

        # 如果时间已过且是一次性提醒，立即触发
        if reminder.trigger_time <= now and reminder.repeat_rule == RepeatRule.NONE:
            logger.info(f"提醒时间已过，立即触发: {reminder.id} - {reminder.title}")
            try:
                self.handler.handle(reminder)
            except Exception as e:
                logger.error(f"立即触发提醒失败: {e}")
            return

        if reminder.repeat_rule == RepeatRule.NONE:
            trigger = DateTrigger(run_date=reminder.trigger_time)
        else:
            cron = self._to_cron(reminder.trigger_time, reminder.repeat_rule)
            trigger = CronTrigger.from_crontab(cron)

        self.scheduler.add_job(
            self.handler.handle,
            trigger=trigger,
            id=reminder.id,
            args=[reminder],
            replace_existing=True,
        )

    def _to_cron(self, trigger_time: datetime, repeat_rule: RepeatRule) -> str:
        """将重复规则转换为 Cron 表达式"""
        if repeat_rule == RepeatRule.DAILY:
            return f"{trigger_time.minute} {trigger_time.hour} * * *"
        elif repeat_rule == RepeatRule.WEEKLY:
            return f"{trigger_time.minute} {trigger_time.hour} * * {trigger_time.weekday()}"
        elif repeat_rule == RepeatRule.MONTHLY:
            return f"{trigger_time.minute} {trigger_time.hour} {trigger_time.day} * *"
        return ""
