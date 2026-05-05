"""MiMo TTS — 小米 MiMo 语音合成。"""

import base64
import logging

logger = logging.getLogger("polaris.voice.mimo_tts")

PRESET_VOICES = ["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]


def mimo_text_to_speech(text: str, voice: str = "冰糖", context: str = "") -> bytes | None:
    """MiMo TTS 语音合成。

    Args:
        text: 要合成的文本
        voice: 预置音色名称
        context: 风格控制指令（可选）

    Returns:
        WAV 音频 bytes，失败返回 None
    """
    try:
        from openai import OpenAI
        from src.core.config import config

        api_key = config.get("voice.api_key") or config.get("llm.api_key", "")
        base_url = config.get("voice.base_url", "https://api.xiaomimimo.com/v1")

        client = OpenAI(api_key=api_key, base_url=base_url)

        messages = []
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "assistant", "content": text[:4096]})

        completion = client.chat.completions.create(
            model=config.get("voice.tts_model", "mimo-v2.5-tts"),
            messages=messages,
            audio={"format": "wav", "voice": voice},
        )

        message = completion.choices[0].message
        if message.audio and getattr(message.audio, "data", None):
            return base64.b64decode(message.audio.data)

        logger.warning("MiMo TTS 未返回音频数据")
        return None

    except Exception as e:
        logger.warning(f"MiMo TTS 失败: {e}")
        return None


def mimo_voicedesign(text: str, context: str) -> bytes | None:
    """MiMo 音色设计 — 文本描述定制音色。

    Args:
        text: 要合成的文本（作为 assistant 回复）
        context: 音色描述指令，如「温柔的女声，带一点鼻音」

    Returns:
        WAV 音频 bytes，失败返回 None
    """
    try:
        from openai import OpenAI
        from src.core.config import config

        api_key = config.get("voice.api_key") or config.get("llm.api_key", "")
        base_url = config.get("voice.base_url", "https://api.xiaomimimo.com/v1")
        client = OpenAI(api_key=api_key, base_url=base_url)

        messages = [
            {"role": "user", "content": context},
            {"role": "assistant", "content": text[:4096]},
        ]

        completion = client.chat.completions.create(
            model="mimo-v2.5-tts-voicedesign",
            messages=messages,
            audio={"format": "wav"},
        )

        message = completion.choices[0].message
        if message.audio and getattr(message.audio, "data", None):
            return base64.b64decode(message.audio.data)

        logger.warning("MiMo 音色设计未返回音频数据")
        return None

    except Exception as e:
        logger.warning(f"MiMo 音色设计失败: {e}")
        return None
