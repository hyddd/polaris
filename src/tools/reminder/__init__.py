from .tool import ReminderTool, create_default
from .setup import get_reminder_store, set_reminder_store, get_reminder_service, set_reminder_service

from src.events import event_bus


def _on_cleanup(**kwargs):
    import json
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


event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
