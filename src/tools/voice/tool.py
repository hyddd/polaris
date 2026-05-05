"""VoiceTool — MiMo TTS 语音合成工具。"""

from typing import Literal, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "VoiceTool":
    return VoiceTool()


class VoiceInput(BaseModel):
    text: str = Field(
        description="要合成语音的文本。如果用户没有指定文本，根据上下文自行编写。"
        "可以在文本中插入音频标签，如（温柔）（叹气）（轻声）（唱歌）。"
    )
    voice: Optional[str] = Field(
        default=None,
        description="音色名称。中文：冰糖(活泼少女)、茉莉(知性女声)、苏打(阳光少年)、白桦(成熟男声)。"
        "英文：Mia(lively girl)、Chloe(sweet dreamy)、Milo(sunny boy)、Dean(steady gentle)。"
        "根据用户语言和内容风格选择。中文默认冰糖，英文默认 Mia。"
    )
    context: Optional[str] = Field(
        default=None,
        description="自然语言风格控制。描述语气、情绪、语速等。"
        "例：'温柔的语气，语速稍慢'、'用孙悟空的风格，豪迈霸气'、'带着哽咽的语气'。"
        "也用于导演模式：描述角色、场景、指导。"
    )
    mode: Literal["preset", "voicedesign"] = Field(
        default="preset",
        description="preset=预置音色，voicedesign=文本描述定制音色"
    )


class VoiceTool(BaseTool):
    name: str = "voice"
    description: str = """MiMo TTS 语音合成。将文字转为语音。

触发条件：用户说"语音回复"、"说出来"、"读一下"、"念一下"、"用xx的声音"、"唱歌"等。

预置音色：
- 中文女声：冰糖(活泼少女)、茉莉(知性女声)
- 中文男声：苏打(阳光少年)、白桦(成熟男声)
- 英文女声：Mia(lively girl)、Chloe(sweet dreamy)
- 英文男声：Milo(sunny boy)、Dean(steady gentle)

音频标签控制：在文本中用括号描述语气情绪，实现句内切换。
- 基础情绪：（开心）（悲伤）（愤怒）（兴奋）（委屈）（平静）
- 复合情绪：（怅然）（欣慰）（无奈）（愧疚）（动情）
- 语调节奏：（温柔）（高冷）（活泼）（严肃）（慵懒）（深沉）
- 音色特质：（磁性）（醇厚）（清亮）（空灵）（甜美）（沙哑）
- 腔调方言：（东北话）（四川话）（粤语）（御姐音）（大叔音）
- 声音动作：（叹气）（轻声）（低语）（笑）（哽咽）（吸气）
- 唱歌：文本最前面加（唱歌）

使用规则：
1. 根据用户语言选择音色，中文用冰糖/茉莉/苏打/白桦，英文用 Mia/Chloe/Milo/Dean
2. 根据内容风格选择音色（活泼用冰糖，严肃用白桦）
3. 如果用户没有指定文本，根据上下文自行编写（2-5句）
4. 如果用户没有指定风格，根据内容自行在文本中插入合适的音频标签增强表现力
5. 标签是调味不是主菜，同一句话最多一个标签
6. 标点有表演意义：省略号=停顿，破折号=拖音
7. 调用一次即可，不要重复调用。返回结果包含音频 URL，直接回复给用户。"""
    args_schema: type[BaseModel] = VoiceInput

    def _run(
        self,
        text: str,
        voice: str | None = None,
        context: str | None = None,
        mode: str = "preset",
    ) -> str:
        from src.domains.voice import get_voice_domain

        domain = get_voice_domain()
        if not domain:
            return "语音服务未就绪。"

        url = domain.synthesize_to_file(text, voice=voice, context=context, mode=mode)
        if not url:
            return "语音合成失败，请检查 voice 配置。"
        return f"语音合成完成。请直接将以下链接发送给用户，不要再调用任何工具：{url}"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
