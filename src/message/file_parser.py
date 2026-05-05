"""文件解析 — 将文件内容提取为文本。"""

import base64
import logging
from pathlib import Path

from .models import Attachment

logger = logging.getLogger("polaris.message.file_parser")


def parse_file(attachment: Attachment) -> str | None:
    """解析文件附件为文本内容。"""
    if attachment.type == "image":
        return None  # 图片不解析为文本

    try:
        content = base64.b64decode(attachment.data)
    except Exception:
        # data 可能是文件路径
        path = Path(attachment.data)
        if path.exists():
            content = path.read_bytes()
        else:
            return None

    mime = attachment.mime_type.lower()
    filename = attachment.filename.lower()

    if mime == "text/plain" or filename.endswith(".txt"):
        return content.decode("utf-8", errors="replace")
    elif mime == "text/markdown" or filename.endswith(".md"):
        return content.decode("utf-8", errors="replace")
    elif "pdf" in mime or filename.endswith(".pdf"):
        return _parse_pdf(content)
    elif "word" in mime or filename.endswith(".docx"):
        return _parse_docx(content)
    elif mime.startswith("audio/") or filename.endswith((".webm", ".wav", ".mp3", ".ogg", ".m4a", ".flac")):
        return _transcribe_audio(content)
    else:
        # 尝试作为文本读取
        try:
            return content.decode("utf-8", errors="replace")[:5000]
        except Exception:
            return None


def _parse_pdf(content: bytes) -> str | None:
    try:
        import fitz

        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)[:10000]
    except ImportError:
        logger.warning("PDF 解析需要安装 pymupdf: pip install pymupdf")
        return "[PDF 解析需要安装 pymupdf]"
    except Exception as e:
        logger.warning(f"PDF 解析失败: {e}")
        return None


def _transcribe_audio(content: bytes) -> str | None:
    """使用 Whisper STT 将音频转为文本。"""
    try:
        from src.domains.voice import get_voice_domain
        domain = get_voice_domain()
        if not domain:
            logger.warning("Voice 域未初始化，无法转写语音")
            return None
        text = domain.transcribe(content)
        if text:
            return text
        return None
    except ImportError:
        logger.warning("STT 依赖未安装，无法转写语音")
        return None
    except Exception as e:
        logger.warning(f"语音转写失败: {e}")
        return None


def _parse_docx(content: bytes) -> str | None:
    try:
        import io

        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)[:10000]
    except ImportError:
        logger.warning("DOCX 解析需要安装 python-docx: pip install python-docx")
        return "[DOCX 解析需要安装 python-docx]"
    except Exception as e:
        logger.warning(f"DOCX 解析失败: {e}")
        return None
