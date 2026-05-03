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


event_bus.subscribe("app:startup", _on_startup)
event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
