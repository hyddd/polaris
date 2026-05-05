"""VoiceTool — MiMo TTS 语音合成工具。

触发场景：
- 用户说"语音回复"、"说出来"、"读一下"、"念一下"
- 用户指定音色或风格（"用温柔的语气"、"用茉莉的声音"）
- 用户要求唱歌
"""

from typing import Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

PRESET_VOICES = ["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]

VOICE_DESCRIPTIONS = {
    "冰糖": "中文女声，活泼少女",
    "茉莉": "中文女声，知性女声",
    "苏打": "中文男声，阳光少年",
    "白桦": "中文男声，成熟男声",
    "Mia": "English female, lively girl",
    "Chloe": "English female, sweet dreamy",
    "Milo": "English male, sunny boy",
    "Dean": "English male, steady gentle",
}


def create_default() -> "VoiceTool":
    return VoiceTool()


class VoiceInput(BaseModel):
    text: str = Field(description="要合成语音的文本内容")
    voice: Optional[str] = Field(
        default=None,
        description=f"音色名称。可选值：{', '.join(PRESET_VOICES)}。不指定则自动选择。",
    )
    context: Optional[str] = Field(
        default=None,
        description="自然语言风格控制指令，如「温柔的语气」「语速稍快」「带着哽咽」。也用于导演模式。",
    )
    mode: Literal["preset", "voicedesign", "voiceclone"] = Field(
        default="preset",
        description="合成模式：preset=预置音色，voicedesign=文本描述定制音色，voiceclone=音频样本复刻",
    )


class VoiceTool(BaseTool):
    name: str = "voice"
    description: str = """MiMo TTS 语音合成。将文字转为语音。

触发条件：用户说"语音回复"、"说出来"、"读一下"、"念一下"、"用xx的声音"、"唱歌"等。

功能：
- 预置音色：冰糖(活泼少女)、茉莉(知性女声)、苏打(阳光少年)、白桦(成熟男声)、Mia/Chloe/Milo/Dean(英文)
- 自然语言风格控制：通过 context 参数描述语气、情绪、语速等
- 音频标签：在文本中用括号描述语气，如（温柔）（叹气）（轻声）
- 唱歌：文本最前面加（唱歌）
- 导演模式：通过 context 描述角色、场景、指导

使用建议：
1. 根据用户语言选择音色（中文用冰糖/茉莉/苏打/白桦，英文用 Mia/Chloe/Milo/Dean）
2. 根据内容风格选择音色（活泼内容用冰糖，严肃内容用白桦）
3. 如果用户没有指定，可以自行在文本中插入合适的音频标签增强表现力
4. 如果用户没有指定文本，根据上下文自行编写合适的文本"""
    args_schema: type[BaseModel] = VoiceInput

    def _run(
        self,
        text: str,
        voice: str | None = None,
        context: str | None = None,
        mode: str = "preset",
    ) -> str:
        from src.core.config import config

        # 自动选择音色
        if not voice:
            voice = config.get("voice.voice", "冰糖")

        if mode == "preset":
            from .mimo_tts import mimo_text_to_speech

            audio = mimo_text_to_speech(
                text,
                voice=voice,
                context=context or config.get("voice.context", ""),
            )
        elif mode == "voicedesign":
            from .mimo_tts import mimo_voicedesign

            audio = mimo_voicedesign(text, context=context or "")
        elif mode == "voiceclone":
            return "音色克隆模式需要提供音频样本文件，请通过 Admin UI 上传。"
        else:
            return f"未知模式：{mode}"

        if not audio:
            return "语音合成失败，请检查 voice 配置。"

        # 保存音频文件
        import uuid
        from pathlib import Path

        output_dir = Path(config.resolve_path("data/voice"))
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
        output_path = output_dir / filename
        output_path.write_bytes(audio)

        return f"语音已生成：{output_path}（{len(audio)} 字节）"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
