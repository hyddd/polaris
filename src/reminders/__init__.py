"""Reminders module."""

# Global instances, set by server.py during startup
_scheduler = None
_reminder_service = None


def get_scheduler():
    """Get the global reminder scheduler instance."""
    return _scheduler


def set_scheduler(scheduler):
    """Set the global reminder scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def get_reminder_service():
    """Get the global ReminderService instance."""
    return _reminder_service


def set_reminder_service(service):
    """Set the global ReminderService instance."""
    global _reminder_service
    _reminder_service = service
