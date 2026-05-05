"""VoiceDomain — 语音合成与识别基础设施。"""

import logging
import uuid
from pathlib import Path

from src.core.config import config
from src.core.events import event_bus

logger = logging.getLogger("polaris.voice")

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


class VoiceDomain:
    def __init__(self):
        self._output_dir = Path(config.resolve_path("data/voice"))
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, text: str, voice: str = None, context: str = None, mode: str = "preset") -> bytes | None:
        """文字转语音，返回音频 bytes。

        Args:
            text: 要合成的文本
            voice: 音色名称
            context: 风格控制指令
            mode: 合成模式 (preset / voicedesign)

        Returns:
            WAV 音频 bytes，失败返回 None
        """
        voice = voice or config.get("voice.voice", "冰糖")
        context = context or config.get("voice.context", "")

        if mode == "preset":
            from .mimo_tts import mimo_text_to_speech
            return mimo_text_to_speech(text, voice=voice, context=context)
        elif mode == "voicedesign":
            from .mimo_tts import mimo_voicedesign
            return mimo_voicedesign(text, context=context)
        else:
            logger.warning(f"不支持的 TTS 模式: {mode}")
            return None

    def synthesize_to_file(self, text: str, voice: str = None, context: str = None, mode: str = "preset") -> Path | None:
        """文字转语音，保存为文件，返回文件路径。"""
        audio = self.synthesize(text, voice=voice, context=context, mode=mode)
        if not audio:
            return None
        filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
        path = self._output_dir / filename
        path.write_bytes(audio)
        return path

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str | None:
        """语音转文字。"""
        from .stt import speech_to_text
        return speech_to_text(audio_data, language=language)

    def list_voices(self) -> list[dict]:
        """列出可用音色。"""
        return [
            {"name": name, "description": VOICE_DESCRIPTIONS.get(name, "")}
            for name in PRESET_VOICES
        ]


_domain: VoiceDomain | None = None


def get_voice_domain() -> VoiceDomain:
    return _domain


def _on_startup(**kwargs):
    global _domain
    _domain = VoiceDomain()


event_bus.subscribe("app:startup", _on_startup)
