"""Reminders module."""

# Global scheduler instance, set by server.py during startup
_scheduler = None


def get_scheduler():
    """Get the global reminder scheduler instance."""
    return _scheduler


def set_scheduler(scheduler):
    """Set the global reminder scheduler instance."""
    global _scheduler
    _scheduler = scheduler
