"""Daily maintenance tick — publishes cleanup:cron for all modules."""

from src.core.infra import event_bus
from src.core.config import config


def _publish_scheduled_cleanup():
    if config.get("cleanup.enabled", True):
        event_bus.publish("cleanup:cron")


def _on_startup(cron=None, **kwargs):
    if not config.get("cleanup.enabled", True):
        return
    cron.add_cron_job(
        _publish_scheduled_cleanup,
        "daily-tick", hour=3, minute=0,
    )


event_bus.subscribe("app:startup", _on_startup)
