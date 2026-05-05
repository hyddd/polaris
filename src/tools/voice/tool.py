"""VoiceTool — MiMo TTS LLM 工具接口。"""

from typing import Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "VoiceTool":
    return VoiceTool()


class VoiceInput(BaseModel):
    text: str = Field(description="要合成语音的文本内容")
    voice: Optional[str] = Field(default=None, description="音色名称")
    context: Optional[str] = Field(default=None, description="风格控制指令")
    mode: Literal["preset", "voicedesign"] = Field(default="preset", description="合成模式")


class VoiceTool(BaseTool):
    name: str = "voice"
    description: str = """MiMo TTS 语音合成。触发条件：用户说"语音回复"、"说出来"、"读一下"、"念一下"、"唱歌"等。
音色：冰糖(活泼少女)、茉莉(知性)、苏打(少年)、白桦(成熟)、Mia/Chloe/Milo/Dean(英文)。
支持自然语言风格控制和音频标签（括号描述语气）。"""
    args_schema: type[BaseModel] = VoiceInput

    def _run(self, text: str, voice: str = None, context: str = None, mode: str = "preset") -> str:
        from src.domains.voice import get_voice_domain
        domain = get_voice_domain()
        if not domain:
            return "语音服务未就绪。"

        path = domain.synthesize_to_file(text, voice=voice, context=context, mode=mode)
        if not path:
            return "语音合成失败，请检查 voice 配置。"
        return f"语音已生成：{path}"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
