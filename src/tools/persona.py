from typing import Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class PersonaInput(BaseModel):
    action: Literal["get", "set"] = Field(
        description="操作类型：get=查看当前人设, set=更新人设"
    )
    name: str | None = Field(default=None, description="助手名称，如「小星」")
    role: str | None = Field(default=None, description="角色，如「私人秘书」「技术顾问」")
    traits: list[str] | None = Field(default=None, description="性格特点列表，如 [\"温柔\", \"专业\"]")
    style: str | None = Field(default=None, description="沟通风格，如「简洁直接」「详细解释」")
    language: str | None = Field(default=None, description="语言偏好，如「中文」「English」")
    extra: str | None = Field(default=None, description="其他自定义描述")


def _persona_to_text(persona: dict) -> str:
    """Format structured persona dict into readable text."""
    parts = []
    if persona.get("name"):
        parts.append(f"名称：{persona['name']}")
    if persona.get("role"):
        parts.append(f"角色：{persona['role']}")
    if persona.get("traits"):
        parts.append(f"性格：{'、'.join(persona['traits'])}")
    if persona.get("style"):
        parts.append(f"风格：{persona['style']}")
    if persona.get("language") and persona["language"] != "中文":
        parts.append(f"语言：{persona['language']}")
    if persona.get("extra"):
        parts.append(f"备注：{persona['extra']}")
    return "\n".join(parts) if parts else ""


class PersonaTool(BaseTool):
    name: str = "persona"
    description: str = (
        "设置或查看当前会话的人设（结构化字段）。"
        "用户说「你是一个...」「你的性格是...」「人设改为...」等时调用 set 更新人设。"
        "只需传入要更新的字段，未传入的字段保持不变。"
        "查看当前人设时调用 get。"
    )
    args_schema: type[BaseModel] = PersonaInput

    def _run(
        self,
        action: str,
        name: str | None = None,
        role: str | None = None,
        traits: list[str] | None = None,
        style: str | None = None,
        language: str | None = None,
        extra: str | None = None,
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
            if role is not None:
                updates["role"] = role.strip()
            if traits is not None:
                updates["traits"] = [t.strip() for t in traits if t.strip()]
            if style is not None:
                updates["style"] = style.strip()
            if language is not None:
                updates["language"] = language.strip()
            if extra is not None:
                updates["extra"] = extra.strip()

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
        role: str | None = None,
        traits: list[str] | None = None,
        style: str | None = None,
        language: str | None = None,
        extra: str | None = None,
    ) -> str:
        return self._run(
            action=action, name=name, role=role, traits=traits,
            style=style, language=language, extra=extra,
        )
