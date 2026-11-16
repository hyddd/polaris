"""Session management endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.session.manager import get_session_manager
from src.core.infra import cleanup_session_locks

router = APIRouter()


class SessionInfo(BaseModel):
    session_id: str
    name: str
    message_count: int
    last_active: str
    summary: str
    is_active: bool


class CreateSessionRequest(BaseModel):
    name: str | None = None


class RenameSessionRequest(BaseModel):
    name: str


@router.get("/api/sessions")
def list_sessions(channel: str = "default"):
    session_mgr = get_session_manager()
    sessions = session_mgr.list_sessions()
    active_session = session_mgr.active_session(channel)
    active_id = active_session.session_id
    return {
        "active_session_id": active_id,
        "sessions": [
            SessionInfo(
                session_id=s.session_id,
                name=s.name,
                message_count=s.metadata.get("message_count", 0),
                last_active=s.last_active,
                summary=s.compressor.summary[:100] if s.compressor.summary else "",
                is_active=(s.session_id == active_id),
            )
            for s in sessions
        ],
    }


@router.post("/api/sessions/{session_id}/activate")
def activate_session(session_id: str, channel: str = "default"):
    session_mgr = get_session_manager()
    result = session_mgr.switch(session_id, channel)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"ok": True, "active_session": result.session_id, "name": result.name}


@router.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    session_mgr = get_session_manager()
    try:
        session = session_mgr.create(name=req.name)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "session_id": session.session_id,
        "name": session.name,
        "created_at": session.created_at,
    }


@router.put("/api/sessions/{session_id}")
def rename_session(session_id: str, req: RenameSessionRequest):
    """按 ID 重命名指定会话。

    以前网页通过聊天命令 `/rename` 改名，而该命令改的是当前激活的会话，
    不是页面上点的那个；而且走聊天入口要拿会话锁，回复进行中时会卡住。
    """
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    session_mgr = get_session_manager()
    if session_mgr.get(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    if any(s.name == name and s.session_id != session_id for s in session_mgr.list_sessions()):
        raise HTTPException(status_code=400, detail=f"已存在同名会话「{name}」")
    session_mgr.rename(session_id, name)
    return {"ok": True, "session_id": session_id, "name": name}


@router.get("/api/sessions/{session_id}")
def get_session_detail(session_id: str):
    session_mgr = get_session_manager()
    session = session_mgr.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    messages = session.memory.get_history()
    compressor = session.compressor
    return {
        "session_id": session.session_id,
        "name": session.name,
        "messages": [
            {
                "id": session.memory.get_message_id(m) or f"msg_{i}",
                "type": m.type,
                "content": m.content if hasattr(m, "content") else "",
            }
            for i, m in enumerate(messages)
        ],
        "summary": compressor.summary,
        "token_stats": {
            "message_count": len(messages),
            "estimated_tokens": compressor._count_tokens(messages) + compressor._summary_tokens,
            "compression_trigger": compressor.compress_trigger,
        },
    }


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    session_mgr = get_session_manager()
    session = session_mgr.get(session_id)
    if session and session.name == "default":
        raise HTTPException(status_code=400, detail="default 会话不能删除")
    if not session_mgr.delete(session_id):
        raise HTTPException(status_code=400, detail=f"Cannot delete session: {session_id}")
    cleanup_session_locks(session_id)
    return {"ok": True}
