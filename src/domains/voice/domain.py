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

    def synthesize_to_file(self, text: str, voice: str = None, context: str = None, mode: str = "preset") -> str | None:
        """文字转语音，保存为文件，返回可访问的 URL 路径。"""
        audio = self.synthesize(text, voice=voice, context=context, mode=mode)
        if not audio:
            return None

        filename = f"tts_{uuid.uuid4().hex[:8]}"

        # 优先转为 silk（QQ 语音条要求）
        silk_data = self._wav_to_silk(audio)
        if silk_data:
            filename += ".silk"
            path = self._output_dir / filename
            path.write_bytes(silk_data)
            return f"/api/voice/{filename}"

        # silk 转换失败，尝试 MP3
        mp3_data = self._wav_to_mp3(audio)
        if mp3_data:
            filename += ".mp3"
            path = self._output_dir / filename
            path.write_bytes(mp3_data)
            return f"/api/voice/{filename}"

        # 都失败，保存原始 WAV
        filename += ".wav"
        path = self._output_dir / filename
        path.write_bytes(audio)
        return f"/api/voice/{filename}"

    def _wav_to_silk(self, wav_data: bytes) -> bytes | None:
        """WAV 转 silk，需要 pilk 库。"""
        import subprocess
        import tempfile

        try:
            import pilk
        except ImportError:
            logger.debug("pilk 未安装，跳过 silk 转换")
            return None

        wav_path = pcm_path = silk_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
                wav_file.write(wav_data)
                wav_path = wav_file.name

            pcm_path = wav_path.replace(".wav", ".pcm")
            silk_path = wav_path.replace(".wav", ".silk")

            # WAV → PCM (16bit, mono, 24000Hz)
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-f", "s16le", "-ar", "24000", "-ac", "1", pcm_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                return None

            # PCM → silk
            pilk.encode(pcm_path, silk_path, pcm_rate=24000, tencent=True)

            return Path(silk_path).read_bytes()
        except Exception as e:
            logger.warning(f"silk 转换失败: {e}")
            return None
        finally:
            for p in [wav_path, pcm_path, silk_path]:
                if p:
                    Path(p).unlink(missing_ok=True)

    def _wav_to_mp3(self, wav_data: bytes) -> bytes | None:
        """WAV 转 MP3，需要 ffmpeg。失败返回 None。"""
        import subprocess
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
                wav_file.write(wav_data)
                wav_path = wav_file.name

            mp3_path = wav_path.replace(".wav", ".mp3")

            result = subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                return Path(mp3_path).read_bytes()
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        finally:
            Path(wav_path).unlink(missing_ok=True)
            Path(mp3_path).unlink(missing_ok=True)

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
