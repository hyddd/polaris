"""Reminder lifecycle — startup, cleanup, scheduling, and calendar sync."""

# ── Global state ──

_reminder_store = None
_reminder_handler = None


# ── Accessors ──

def get_reminder_store():
    return _reminder_store


def get_reminder_handler():
    return _reminder_handler


# ── Scheduling helpers ──

def schedule_reminder(reminder):
    """根据提醒的重复规则调度到 cron 中。"""
    import logging
    from datetime import datetime
    from src.cron import get_cron_scheduler
    from .models import RepeatRule

    logger = logging.getLogger("polaris.tools.reminder")
    cron = get_cron_scheduler()
    handler = get_reminder_handler()
    if not cron or not handler:
        return

    if reminder.repeat_rule == RepeatRule.NONE:
        now = datetime.now()
        if reminder.trigger_time <= now:
            logger.info(f"提醒时间已过，立即触发: {reminder.id} - {reminder.title}")
            handler.handle(reminder)
        else:
            cron.add_date_job(handler.handle, reminder.trigger_time, reminder.id, args=[reminder])
    else:
        kwargs = repeat_rule_to_cron_kwargs(reminder.trigger_time, reminder.repeat_rule)
        cron.add_cron_job(handler.handle, reminder.id, args=[reminder], **kwargs)


def repeat_rule_to_cron_kwargs(trigger_time, repeat_rule):
    """将重复规则转换为 APScheduler CronTrigger 关键字参数。"""
    from .models import RepeatRule

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


# ── Event handlers ──

def _on_startup(cron=None, channels=None, **kwargs):
    """框架就绪后自初始化：加载活跃提醒并注册到 cron。"""
    import logging
    from src.core.config import config
    from .store import ReminderStore
    from .handler import ReminderHandler

    global _reminder_store, _reminder_handler
    logger = logging.getLogger("polaris.tools.reminder")
    path = str(config.resolve_path(config.get("storage.reminders_file", "data/reminders.json")))
    store = ReminderStore(path)
    handler = ReminderHandler(channels or [], store=store)
    _reminder_store = store
    _reminder_handler = handler

    for r in store.list_active():
        schedule_reminder(r)
    logger.info(f"提醒模块已初始化，加载 {len(store.list_all())} 条提醒")


def _on_cleanup(**kwargs):
    import logging
    from datetime import datetime, timedelta
    from src.core.config import config

    logger = logging.getLogger("polaris.tools.reminder")
    store = get_reminder_store()
    if not store:
        return

    retention = config.get("cleanup.reminders_retention_days", 7)
    cutoff = datetime.now() - timedelta(days=retention)
    count = 0

    for r in store.list_all():
        if r.status.value == "cancelled" and r.trigger_time < cutoff:
            store.delete(r.id)
            count += 1

    if count:
        logger.info(f"清理 {count} 条过期提醒（保留 {retention} 天）")


def _on_calendar_created(event_id=None, title=None, event_time_str=None, channel="admin", session_id="", **kwargs):
    from datetime import datetime, timedelta
    from .models import Reminder, RepeatRule, ReminderStatus
    import logging
    logger = logging.getLogger("polaris.tools.reminder")

    store = get_reminder_store()
    handler = get_reminder_handler()
    if not store or not handler:
        return

    try:
        event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
        reminder_time = event_datetime - timedelta(minutes=15)
        is_past = reminder_time <= datetime.now()
        status = ReminderStatus.CANCELLED if is_past else ReminderStatus.ACTIVE

        r = Reminder(
            title=f"{title} 即将开始",
            description=f"日程「{title}」将在15分钟后开始",
            trigger_time=reminder_time,
            repeat_rule=RepeatRule.NONE,
            event_id=event_id,
            channel=channel or "admin",
            session_id=session_id or "",
            status=status,
        )
        store.create(r)
        if not is_past:
            schedule_reminder(r)
        logger.info(f"已创建日程关联提醒: {r.id} @ {reminder_time}")
    except Exception as e:
        logger.error(f"创建日程关联提醒失败: {e}")


def _on_calendar_updated(event_id=None, title=None, event_time_str=None, **kwargs):
    from datetime import datetime, timedelta
    from .models import ReminderStatus
    from src.cron import get_cron_scheduler
    import logging
    logger = logging.getLogger("polaris.tools.reminder")

    store = get_reminder_store()
    if not store:
        return

    cron = get_cron_scheduler()
    handler = get_reminder_handler()

    for reminder in store.find_by_event_id(event_id):
        try:
            event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            new_reminder_time = event_datetime - timedelta(minutes=15)
            new_title = f"{title} 即将开始"

            store.update(reminder.id, trigger_time=new_reminder_time, title=new_title)
            if new_reminder_time > datetime.now():
                store.update(reminder.id, status=ReminderStatus.ACTIVE)
            reminder = store.get(reminder.id)

            if cron and handler:
                cron.remove_job(reminder.id)
                if new_reminder_time > datetime.now():
                    schedule_reminder(reminder)
            logger.info(f"已更新日程关联提醒: {reminder.id} @ {new_reminder_time}")
        except Exception as e:
            logger.error(f"更新日程关联提醒失败: {e}")


def _on_calendar_deleted(event_id=None, **kwargs):
    from src.cron import get_cron_scheduler
    import logging
    logger = logging.getLogger("polaris.tools.reminder")

    store = get_reminder_store()
    if not store:
        return

    cron = get_cron_scheduler()
    for reminder in store.find_by_event_id(event_id):
        try:
            if store.delete(reminder.id):
                if cron:
                    cron.remove_job(reminder.id)
                logger.info(f"已删除日程关联提醒: {reminder.id}")
        except Exception as e:
            logger.error(f"删除日程关联提醒失败: {e}")


# ── Subscriptions ──

from src.core.events import event_bus
event_bus.subscribe("app:startup", _on_startup)
event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
event_bus.subscribe("calendar:event_created", _on_calendar_created)
event_bus.subscribe("calendar:event_updated", _on_calendar_updated)
event_bus.subscribe("calendar:event_deleted", _on_calendar_deleted)
