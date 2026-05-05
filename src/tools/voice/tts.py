"""Text-to-Speech — 向后兼容的便捷函数，内部调用 VoiceDomain。"""

import logging

logger = logging.getLogger("polaris.voice.tts")


def text_to_speech(text: str, voice: str = None) -> bytes | None:
    """文字转语音。内部委托给 VoiceDomain。

    Args:
        text: 要转换的文字
        voice: 声音名称（可选，None 时使用配置默认值）

    Returns:
        音频 bytes，失败返回 None
    """
    from src.domains.voice import get_voice_domain
    domain = get_voice_domain()
    if not domain:
        logger.warning("语音服务未就绪")
        return None
    return domain.synthesize(text, voice=voice)
