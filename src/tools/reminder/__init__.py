from .tool import ReminderTool, create_default
from .setup import get_reminder_store, set_reminder_store, get_reminder_service, set_reminder_service

from src.events import event_bus


def _on_startup(cron=None, channels=None, **kwargs):
    """框架就绪后自初始化：加载活跃提醒并注册到 cron。"""
    import logging
    from src.config import config
    from .store import ReminderStore
    from .handler import ReminderHandler
    from .setup import reminder_setup

    logger = logging.getLogger("polaris.tools.reminder")
    path = str(config.resolve_path(config.get("storage.reminders_file", "data/reminders.json")))
    store = ReminderStore(path)
    handler = ReminderHandler(channels or [])
    handler.set_store(store)
    reminder_setup(cron, store, handler)
    logger.info(f"提醒模块已初始化，加载 {len(store.list_all())} 条提醒")


def _on_cleanup(**kwargs):
    import logging
    from datetime import datetime, timedelta
    from src.config import config

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
    """日程创建 → 自动创建关联提醒。"""
    service = get_reminder_service()
    if service:
        service.create_event_reminder(title, event_time_str, event_id, channel, session_id)


def _on_calendar_updated(event_id=None, title=None, event_time_str=None, **kwargs):
    """日程更新 → 更新关联提醒时间。"""
    service = get_reminder_service()
    if service and event_id:
        service.update_event_reminder(event_id, title, event_time_str)


def _on_calendar_deleted(event_id=None, **kwargs):
    """日程删除 → 删除关联提醒。"""
    service = get_reminder_service()
    if service and event_id:
        service.delete_event_reminder(event_id)


event_bus.subscribe("app:startup", _on_startup)
event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
event_bus.subscribe("calendar:event_created", _on_calendar_created)
event_bus.subscribe("calendar:event_updated", _on_calendar_updated)
event_bus.subscribe("calendar:event_deleted", _on_calendar_deleted)
