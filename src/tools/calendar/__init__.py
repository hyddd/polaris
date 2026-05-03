from .tool import GoogleCalendarTool, create_default

from src.events import event_bus


def _on_cleanup(**kwargs):
    import json
    import logging
    from datetime import datetime, timedelta
    from src.config import config

    logger = logging.getLogger("polaris.tools.calendar")
    path = config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else []
    retention = config.get("cleanup.calendar_retention_days", 14)
    cutoff = (datetime.now() - timedelta(days=retention)).strftime("%Y-%m-%d")
    kept = [e for e in events if e.get("date", "") >= cutoff]
    archived = len(events) - len(kept)

    if archived:
        from src.storage.atomic import _atomic_write
        _atomic_write(path, kept)
        logger.info(f"清理 {archived} 条过期日程（保留 {retention} 天）")


event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
