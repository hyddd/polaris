from typing import Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class PersonaInput(BaseModel):
    action: Literal["get", "set"] = Field(
        description="操作类型：get=查看当前人设, set=更新人设"
    )
    content: str | None = Field(
        default=None, description="set 时使用：新人设内容，完整替换当前人设"
    )


class PersonaTool(BaseTool):
    name: str = "persona"
    description: str = (
        "设置或查看当前会话的人设。"
        "用户说「你是一个...」「你的性格是...」「人设改为...」等时调用 set 更新人设。"
        "查看当前人设时调用 get。"
    )
    args_schema: type[BaseModel] = PersonaInput

    def _run(self, action: str, content: str | None = None) -> str:
        from src.session.manager import get_session_manager

        session_mgr = get_session_manager()
        session = session_mgr.active_session()

        if action == "get":
            if session.persona:
                return f"当前人设：\n{session.persona}"
            return "当前会话没有人设。"

        if action == "set":
            if not content:
                return "请提供人设内容。"
            session.persona = content.strip()
            session_mgr.save()
            return f"人设已更新。"

        return "未知操作。"

    async def _arun(self, action: str, content: str | None = None) -> str:
        return self._run(action=action, content=content)
