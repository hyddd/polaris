"""VoiceTool — LLM 可调用的语音工具。"""

from typing import Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "VoiceTool":
    return VoiceTool()


class VoiceInput(BaseModel):
    action: Literal["tts"] = Field(description="操作类型: tts=文字转语音")
    text: str = Field(description="要转为语音的文字")


class VoiceTool(BaseTool):
    name: str = "voice"
    description: str = "将文字转为语音。用于需要语音回复的场景。"
    args_schema: type[BaseModel] = VoiceInput

    def _run(self, action: str, text: str) -> str:
        if action == "tts":
            from .tts import text_to_speech

            result = text_to_speech(text)
            if result:
                return f"语音已生成（{len(result)} 字节）。"
            return "语音生成失败。"
        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
