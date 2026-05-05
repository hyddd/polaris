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
        from src.domains.persona import get_persona_domain

        domain = get_persona_domain()
        if not domain:
            return "人设服务未就绪，请稍后重试。"

        if action == "get":
            persona = domain.get_persona(_session_id)
            text = persona.to_text()
            if text:
                return f"当前人设：\n{text}"
            return "当前会话没有人设。"

        if action == "set":
            kwargs = {}
            if name is not None:
                kwargs["name"] = name.strip()
            if call_user is not None:
                kwargs["call_user"] = call_user.strip()
            if identity is not None:
                kwargs["identity"] = identity.strip()
            if personality is not None:
                kwargs["personality"] = personality.strip()
            if timezone is not None:
                kwargs["timezone"] = timezone.strip()
            if notes is not None:
                kwargs["notes"] = notes.strip()

            if not kwargs:
                return "请提供至少一个人设字段。"

            persona = domain.set_persona(_session_id, **kwargs)
            text = persona.to_text()
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
