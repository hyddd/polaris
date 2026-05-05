"""Admin API: Data management (calendar/todos)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain

router = APIRouter()


def _require_calendar_domain():
    from src.domains.calendar import get_calendar_domain
    return require_domain(get_calendar_domain, "日历")


def _require_todo_domain():
    from src.domains.todos import get_todo_domain
    return require_domain(get_todo_domain, "待办")


class DataUpdate(BaseModel):
    data: list | dict


@router.get("/api/data/{data_type}")
def list_data(data_type: str):
    if data_type == "calendar":
        domain = _require_calendar_domain()
        items = [e.to_dict() for e in domain.list_events()]
    elif data_type == "todos":
        domain = _require_todo_domain()
        items = [t.to_dict() for t in domain.list_todos("all")]
    else:
        raise HTTPException(400, f"Unknown type: {data_type}")
    return {"items": items}


@router.post("/api/data/{data_type}")
def create_data(data_type: str, req: DataUpdate):
    if data_type == "calendar":
        domain = _require_calendar_domain()
        d = req.data if isinstance(req.data, dict) else {}
        domain.create_event(
            date=d.get("date", ""),
            title=d.get("title", ""),
            time=d.get("time", "09:00"),
            duration=d.get("duration", 60),
            attendees=d.get("attendees"),
        )
    elif data_type == "todos":
        domain = _require_todo_domain()
        d = req.data if isinstance(req.data, dict) else {}
        domain.create_todo(
            title=d.get("title", ""),
            priority=d.get("priority", "medium"),
            due=d.get("due", ""),
        )
    else:
        raise HTTPException(400, f"Unknown type: {data_type}")
    return {"ok": True}


@router.put("/api/data/{data_type}/{item_id}")
def update_data(data_type: str, item_id: str, req: DataUpdate):
    if data_type == "todos":
        domain = _require_todo_domain()
        updates = req.data if isinstance(req.data, dict) else {}
        result = domain.update_todo(item_id, updates)
        if result is None:
            raise HTTPException(404, f"Item not found: {item_id}")
    else:
        raise HTTPException(400, f"Update not supported for {data_type}")
    return {"ok": True}


@router.delete("/api/data/{data_type}/{item_id}")
def delete_data(data_type: str, item_id: str):
    if data_type == "calendar":
        domain = _require_calendar_domain()
        if not domain.delete_event(item_id):
            raise HTTPException(404, "日程不存在")
    elif data_type == "todos":
        domain = _require_todo_domain()
        if not domain.delete_todo(item_id):
            raise HTTPException(404, f"Item not found: {item_id}")
    else:
        raise HTTPException(400, f"Delete not supported for {data_type}")
    return {"ok": True}
