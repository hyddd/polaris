"""Admin API: System status."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/status")
def get_status():
    from src.core.tools.registry import ToolRegistry
    from src.domains.scheduler import get_scheduler_domain
    from src.core.channel.loader import _discovered_channels

    registry = ToolRegistry.get_instance()
    tools = [{"name": t.name} for t in registry.list_tools()]

    scheduler = get_scheduler_domain()
    jobs = [j.to_dict() for j in scheduler.list_jobs()] if scheduler else []

    channels = []
    for ch in _discovered_channels:
        channels.append({
            "name": ch.name,
            "configured": ch.is_configured(),
        })

    return {"tools": tools, "jobs": jobs, "channels": channels}
