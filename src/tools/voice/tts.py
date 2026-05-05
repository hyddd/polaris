"""Text-to-Speech — 文字转语音（OpenAI TTS API）。"""

import logging

logger = logging.getLogger("polaris.voice.tts")


def text_to_speech(text: str, voice: str = "alloy") -> bytes | None:
    """将文字转为音频。

    Args:
        text: 要转换的文字
        voice: 声音类型，可选 alloy/echo/fable/onyx/nova/shimmer

    Returns:
        MP3 音频 bytes，失败返回 None
    """
    try:
        import openai
        from src.core.config import config

        client = openai.OpenAI(
            api_key=config.get("voice.api_key") or config.get("llm.api_key", ""),
            base_url=config.get("voice.base_url") or config.get("llm.base_url"),
        )

        response = client.audio.speech.create(
            model=config.get("voice.tts_model", "tts-1"),
            voice=voice,
            input=text[:4096],  # TTS 有长度限制
        )
        return response.content

    except ImportError:
        logger.warning("语音合成需要 openai 库")
        return None
    except Exception as e:
        logger.warning(f"语音合成失败: {e}")
        return None
