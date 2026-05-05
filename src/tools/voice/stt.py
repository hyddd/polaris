"""Speech-to-Text — 向后兼容的便捷函数，内部调用 VoiceDomain。"""

import logging

logger = logging.getLogger("polaris.voice.stt")


def speech_to_text(audio_data: bytes, language: str = "zh") -> str | None:
    """将音频数据转为文字。内部委托给 VoiceDomain。

    Args:
        audio_data: 音频文件的 bytes 内容
        language: 语言代码，默认中文

    Returns:
        识别出的文字，失败返回 None
    """
    from src.domains.voice import get_voice_domain
    domain = get_voice_domain()
    if not domain:
        logger.warning("语音服务未就绪")
        return None
    return domain.transcribe(audio_data, language=language)
