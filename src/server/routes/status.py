"""Admin API: System status."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/instance")
def get_instance():
    """本服务的模式和名字。personal 连 team 前用它确认对方确实是团队服务；TUI/网页用它显示。"""
    from src.core.db import instance_info
    return instance_info()


@router.get("/api/status")
def get_status():
    from src.core.tools.registry import ToolRegistry
    from src.domains.scheduler import get_scheduler_domain
    from src.core.channel.loader import get_discovered_channels

    registry = ToolRegistry.get_instance()
    tools = [{"name": t.name} for t in registry.list_tools()]

    scheduler = get_scheduler_domain()
    jobs = [j.to_dict() for j in scheduler.list_jobs()] if scheduler else []

    channels = []
    for ch in get_discovered_channels():
        channels.append({
            "name": ch.name,
            "configured": ch.is_configured(),
        })

    from src.core.db import instance_info
    return {"tools": tools, "jobs": jobs, "channels": channels, "instance": instance_info(), "team": _team_status()}


def _team_status() -> dict | None:
    """personal 连着团队服务时：现在连得上吗。"""
    from src.core.db import get_remote, RemoteError
    client = get_remote()
    if client is None:
        return None
    try:
        info = client.get("/api/instance")
        return {"ok": True, "name": info.get("name", ""), "url": client.base_url}
    except RemoteError as e:
        return {"ok": False, "error": str(e), "url": client.base_url}
