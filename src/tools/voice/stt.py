"""Speech-to-Text — 语音转文字（OpenAI Whisper API）。"""

import logging
from pathlib import Path

logger = logging.getLogger("polaris.voice.stt")


def speech_to_text(audio_data: bytes, language: str = "zh") -> str | None:
    """将音频数据转为文字。

    Args:
        audio_data: 音频文件的 bytes 内容
        language: 语言代码，默认中文

    Returns:
        识别出的文字，失败返回 None
    """
    try:
        import openai
        from src.core.config import config

        client = openai.OpenAI(
            api_key=config.get("voice.api_key") or config.get("llm.api_key", ""),
            base_url=config.get("voice.base_url") or config.get("llm.base_url"),
        )

        # 创建临时文件（Whisper API 需要文件对象）
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_data)
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model=config.get("voice.stt_model", "whisper-1"),
                    file=f,
                    language=language,
                )
            return response.text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except ImportError:
        logger.warning("语音识别需要 openai 库")
        return None
    except Exception as e:
        logger.warning(f"语音识别失败: {e}")
        return None
