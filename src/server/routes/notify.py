"""通知接口：查看通知目标、主动发送通知（供 CI、脚本和网页"通知"页面调用）。

鉴权：配置了 notify.api_token 时，请求头必须带 Authorization: Bearer <notify.api_token>；
为空时不校验，直接放行（此时由 server.admin_token 的通用鉴权决定，它为空则不鉴权）。
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


def _check_token(request: Request) -> None:
    from src.core.config import config
    token = str(config.get("notify.api_token", "") or "")
    if token and request.headers.get("authorization", "") != f"Bearer {token}":
        raise HTTPException(401, "通知接口令牌错误或缺失（Authorization: Bearer <notify.api_token>）")


class NotifySend(BaseModel):
    targets: list[str] = Field(description="通知目标名称")
    title: str = ""
    content: str = ""
    source: str = Field(default="", description="来源，如 CI、网页，写在消息末尾")


@router.get("/api/notify/targets")
def notify_targets(request: Request):
    _check_token(request)
    from src.domains.notify import list_targets
    return {"targets": list_targets()}


@router.post("/api/notify/send")
def notify_send(req: NotifySend, request: Request):
    _check_token(request)
    from src.domains.notify import NotifyError, send_notification
    try:
        results = send_notification(req.targets, req.title, req.content, source=req.source or "接口")
    except NotifyError as e:
        raise HTTPException(400, str(e))
    if results and all("频率限制" in (r.get("error") or "") for r in results):
        raise HTTPException(429, "所有目标都超过频率限制，请稍后再试")
    return {"results": results}
