"""Text-to-Speech — 文字转语音（支持 MiMo / OpenAI 后端）。"""

import logging

logger = logging.getLogger("polaris.voice.tts")


def text_to_speech(text: str, voice: str = None) -> bytes | None:
    """文字转语音。自动检测后端（MiMo 或 OpenAI）。

    Args:
        text: 要转换的文字
        voice: 声音名称（可选，None 时使用配置默认值）

    Returns:
        音频 bytes，失败返回 None
    """
    from src.core.config import config

    base_url = config.get("voice.base_url", "")
    tts_model = config.get("voice.tts_model", "")

    # MiMo TTS 使用 chat.completions API
    if "mimo" in base_url or "mimo" in tts_model:
        from .mimo_tts import mimo_text_to_speech
        voice = voice or config.get("voice.voice", "冰糖")
        context = config.get("voice.context", "")
        return mimo_text_to_speech(text, voice=voice, context=context)

    # OpenAI TTS 使用 /audio/speech API
    return _openai_text_to_speech(text, voice)


def _openai_text_to_speech(text: str, voice: str = None) -> bytes | None:
    """OpenAI TTS 语音合成。

    Args:
        text: 要转换的文字
        voice: 声音类型，可选 alloy/echo/fable/onyx/nova/shimmer

    Returns:
        MP3 音频 bytes，失败返回 None
    """
    try:
        from src.core.config import config
        base_url = config.get("voice.base_url")
        if not base_url:
            logger.debug("语音合成未配置 voice.base_url，跳过")
            return None

        import openai

        client = openai.OpenAI(
            api_key=config.get("voice.api_key") or config.get("llm.api_key", ""),
            base_url=config.get("voice.base_url") or config.get("llm.base_url"),
        )

        response = client.audio.speech.create(
            model=config.get("voice.tts_model", "tts-1"),
            voice=voice or config.get("voice.voice", "alloy"),
            input=text[:4096],  # TTS 有长度限制
        )
        return response.content

    except ImportError:
        logger.warning("语音合成需要 openai 库")
        return None
    except Exception as e:
        logger.warning(f"语音合成失败: {e}")
        return None
