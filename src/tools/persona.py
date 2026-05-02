from typing import Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class PersonaInput(BaseModel):
    action: Literal["get", "set"] = Field(
        description="操作类型：get=查看当前人设, set=更新人设"
    )
    name: str | None = Field(default=None, description="助手名称，如「诸葛亮」")
    call_user: str | None = Field(default=None, description="称呼用户，如「主公」")
    pronouns: str | None = Field(default=None, description="代词，如「他/她」")
    timezone: str | None = Field(default=None, description="时区，如「Asia/Shanghai」")
    notes: str | None = Field(default=None, description="自由备注，包含角色扮演设定、身份、性格等")


def _persona_to_text(persona: dict) -> str:
    """Format structured persona dict into readable text."""
    parts = []
    if persona.get("name"):
        parts.append(f"名称：{persona['name']}")
    if persona.get("call_user"):
        parts.append(f"称呼用户：{persona['call_user']}")
    if persona.get("pronouns"):
        parts.append(f"代词：{persona['pronouns']}")
    if persona.get("timezone") and persona["timezone"] != "Asia/Shanghai":
        parts.append(f"时区：{persona['timezone']}")
    if persona.get("notes"):
        parts.append(f"备注：{persona['notes']}")
    return "\n".join(parts) if parts else ""


class PersonaTool(BaseTool):
    name: str = "persona"
    description: str = (
        "设置助手身份和角色。用户说「你是诸葛亮，叫我主公」时，解析并设置对应字段。"
        "只需传入要更新的字段，未传入的字段保持不变。"
        "查看当前人设时调用 get。"
    )
    args_schema: type[BaseModel] = PersonaInput

    def _run(
        self,
        action: str,
        name: str | None = None,
        call_user: str | None = None,
        pronouns: str | None = None,
        timezone: str | None = None,
        notes: str | None = None,
    ) -> str:
        from src.session.manager import get_session_manager

        session_mgr = get_session_manager()
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
            if pronouns is not None:
                updates["pronouns"] = pronouns.strip()
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
        pronouns: str | None = None,
        timezone: str | None = None,
        notes: str | None = None,
    ) -> str:
        return self._run(
            action=action, name=name, call_user=call_user,
            pronouns=pronouns, timezone=timezone, notes=notes,
        )
