"""PersonaDomain — 会话人设管理核心服务。"""

import logging

from src.core.events import event_bus
from .models import Persona

logger = logging.getLogger("polaris.persona")


class PersonaDomain:
    """会话人设管理。通过 SessionManager 访问数据，不自己管理存储。"""

    def __init__(self, session_mgr):
        self._session_mgr = session_mgr

    def get_persona(self, session_id: str | None = None) -> Persona:
        """获取会话人设。session_id 为 None 时用 context 中的。"""
        session = self._resolve_session(session_id)
        if not session:
            return Persona()
        return Persona.from_dict(session.persona)

    def set_persona(self, session_id: str | None = None, **kwargs) -> Persona:
        """更新会话人设（部分更新）。"""
        session = self._resolve_session(session_id)
        if not session:
            logger.warning(f"set_persona 失败：未找到会话 {session_id}")
            return Persona()

        persona = Persona.from_dict(session.persona)
        persona.update(kwargs)
        session.persona = persona.to_dict()
        self._session_mgr.save()

        event_bus.publish("persona:persona_changed",
                          session_id=session.session_id,
                          name=persona.name,
                          identity=persona.identity)
        logger.info(f"已更新人设: session={session.session_id}")
        return persona

    def list_personas(self) -> list[tuple[str, Persona]]:
        """列出所有会话的人设。"""
        result = []
        for session in self._session_mgr.list_sessions():
            result.append((session.session_id, Persona.from_dict(session.persona)))
        return result

    def _resolve_session(self, session_id: str | None):
        """根据 session_id 获取 session，为 None 时用 context 中的。"""
        if session_id:
            return self._session_mgr.get(session_id)
        from src.core.context import get_session_id as _ctx_session_id
        sid = _ctx_session_id()
        if sid:
            return self._session_mgr.get(sid)
        return self._session_mgr.active_session()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: PersonaDomain | None = None


def get_persona_domain() -> PersonaDomain:
    return _domain


def set_persona_domain(domain: PersonaDomain | None):
    global _domain
    _domain = domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(**kwargs):
    from src.session.manager import get_session_manager
    global _domain
    _domain = PersonaDomain(get_session_manager())
    logger.info("人设域已启动")


event_bus.subscribe("app:startup", _on_startup)
