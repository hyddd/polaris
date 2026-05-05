"""Admin API: Reminders management."""
from datetime import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain

router = APIRouter()


def _require_reminder_domain():
    from src.domains.reminder import get_reminder_domain
    return require_domain(get_reminder_domain, "提醒")


class ReminderCreate(BaseModel):
    title: str
    description: str = ""
    trigger_time: str  # ISO format datetime string
    repeat_rule: str = "none"


@router.get("/api/reminders")
def list_reminders():
    domain = _require_reminder_domain()
    reminders = domain.list_all()
    return {"items": [r.to_dict() for r in reminders]}


@router.post("/api/reminders")
def create_reminder(req: ReminderCreate):
    domain = _require_reminder_domain()
    try:
        trigger_time = dt.fromisoformat(req.trigger_time)
    except ValueError:
        raise HTTPException(400, "Invalid trigger_time format, expected ISO datetime")
    reminder = domain.create(
        title=req.title,
        trigger_time=trigger_time,
        repeat_rule=req.repeat_rule,
        description=req.description,
    )
    return reminder.to_dict()


@router.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    if not domain.delete(reminder_id):
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return {"ok": True}


@router.post("/api/reminders/{reminder_id}/pause")
def pause_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    r = domain.pause(reminder_id)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()


@router.post("/api/reminders/{reminder_id}/resume")
def resume_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    r = domain.resume(reminder_id)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()
