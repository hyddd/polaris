"""路由共享依赖。"""
from contextlib import contextmanager

from fastapi import HTTPException


def require_domain(getter, name: str):
    """获取 domain 实例，未就绪时抛 503。"""
    domain = getter()
    if not domain:
        raise HTTPException(503, f"{name}服务未就绪")
    return domain


@contextmanager
def scope_errors():
    """公共/私有相关错误转成 HTTP：scope 不合法或公共库未启用 → 400；公共库连不上 → 503。"""
    from src.core.db import ScopeError, DatabaseError
    try:
        yield
    except ScopeError as e:
        raise HTTPException(400, str(e))
    except DatabaseError as e:
        raise HTTPException(503, str(e))


# 网页管理端的 channel。REST 接口只有网页在调，这里创建的日程/提醒都投递给网页。
ADMIN_CHANNEL = "admin"


def admin_delivery_target() -> dict:
    """网页端创建日程/提醒时的投递目标：admin 渠道 + 网页当前激活的会话。

    以前这些接口不传 session_id（默认空串），提醒到点找不到会话、直接丢弃并标成已完成。
    """
    from src.session.manager import get_session_manager
    session = get_session_manager().active_session(ADMIN_CHANNEL)
    return {"channel": ADMIN_CHANNEL, "session_id": session.session_id}
