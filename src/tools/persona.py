from typing import Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "PersonaTool":
    """Factory for auto-discovery. Creates a PersonaTool with default config."""
    return PersonaTool()


class PersonaInput(BaseModel):
    model_config = {"extra": "allow"}

    action: Literal["get", "set"] = Field(
        description="操作类型：get=查看当前人设, set=更新人设"
    )
    name: str | None = Field(default=None, description="助手名称，如「诸葛亮」")
    call_user: str | None = Field(default=None, description="称呼用户，如「主公」")
    identity: str | None = Field(default=None, description="身份设定，如「私人秘书」「刘备的军师」")
    personality: str | None = Field(default=None, description="性格特点，如「沉稳睿智」「温柔亲切」")
    timezone: str | None = Field(default=None, description="时区，如「Asia/Shanghai」")
    notes: str | None = Field(default=None, description="自由备注")


def _persona_to_text(persona: dict) -> str:
    """Format structured persona dict into readable text."""
    parts = []
    if persona.get("name"):
        parts.append(f"名称：{persona['name']}")
    if persona.get("call_user"):
        parts.append(f"称呼用户：{persona['call_user']}")
    if persona.get("identity"):
        parts.append(f"身份：{persona['identity']}")
    if persona.get("personality"):
        parts.append(f"性格：{persona['personality']}")
    if persona.get("timezone") and persona["timezone"] != "Asia/Shanghai":
        parts.append(f"时区：{persona['timezone']}")
    if persona.get("notes"):
        parts.append(f"备注：{persona['notes']}")
    return "\n".join(parts) if parts else ""


class PersonaTool(BaseTool):
    name: str = "persona"
    description: str = (
        "设置助手身份和角色。用户说「你是诸葛亮，叫我主公」时，解析并设置对应字段。"
        "支持设置身份设定(identity)和性格特点(personality)。"
        "只需传入要更新的字段，未传入的字段保持不变。"
        "查看当前人设时调用 get。"
    )
    args_schema: type[BaseModel] = PersonaInput

    def _run(
        self,
        action: str,
        name: str | None = None,
        call_user: str | None = None,
        identity: str | None = None,
        personality: str | None = None,
        timezone: str | None = None,
        notes: str | None = None,
        _session_id: str | None = None,
    ) -> str:
        from src.session.manager import get_session_manager

        session_mgr = get_session_manager()
        # Use _session_id if provided, otherwise fall back to default
        if _session_id:
            session = session_mgr.get(_session_id)
            if not session:
                return f"未找到会话：{_session_id}"
        else:
            session = session_mgr.active_session()

        if action == "get":
            text = _persona_to_text(session.persona)
            if text:
                return f"当前人设：\n{text}"
            return "当前会话没有人设。"

        if action == "set":
            updates = {}
            if name is not None:
                updates["name"] = name.strip()
            if call_user is not None:
                updates["call_user"] = call_user.strip()
            if identity is not None:
                updates["identity"] = identity.strip()
            if personality is not None:
                updates["personality"] = personality.strip()
            if timezone is not None:
                updates["timezone"] = timezone.strip()
            if notes is not None:
                updates["notes"] = notes.strip()

            if not updates:
                return "请提供至少一个人设字段。"

            session.persona.update(updates)
            session_mgr.save()
            text = _persona_to_text(session.persona)
            return f"人设已更新：\n{text}"

        return "未知操作。"

    async def _arun(
        self,
        action: str,
        name: str | None = None,
        call_user: str | None = None,
        identity: str | None = None,
        personality: str | None = None,
        timezone: str | None = None,
        notes: str | None = None,
        _session_id: str | None = None,
    ) -> str:
        return self._run(
            action=action, name=name, call_user=call_user,
            identity=identity, personality=personality,
            timezone=timezone, notes=notes, _session_id=_session_id,
        )
