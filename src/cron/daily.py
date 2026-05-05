"""Daily maintenance tick — publishes cleanup:cron for all modules."""

from src.core.infra import event_bus


def _on_startup(cron=None, **kwargs):
    cron.add_cron_job(
        lambda: event_bus.publish("cleanup:cron"),
        "daily-tick", hour=3, minute=0,
    )


event_bus.subscribe("app:startup", _on_startup)
