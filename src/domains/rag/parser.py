"""文档解析器 — 支持 PDF/DOCX/TXT/MD。"""

import logging
from pathlib import Path

logger = logging.getLogger("polaris.rag.parser")


class DocumentParser:
    """多格式文档解析器。"""

    def parse_file(self, file_path: str) -> str | None:
        """解析文件为文本。"""
        path = Path(file_path)
        if not path.exists():
            return None
        return self.parse_bytes(path.read_bytes(), path.name)

    def parse_bytes(self, data: bytes, filename: str) -> str | None:
        """解析文件 bytes 为文本。"""
        suffix = Path(filename).suffix.lower()

        if suffix in (".txt", ".md", ".markdown"):
            return data.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            return self._parse_pdf(data)
        elif suffix == ".docx":
            return self._parse_docx(data)
        else:
            # 尝试作为文本读取
            try:
                return data.decode("utf-8", errors="replace")[:50000]
            except Exception:
                return None

    def _parse_pdf(self, data: bytes) -> str | None:
        """解析 PDF 文件。"""
        try:
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)[:50000]
        except ImportError:
            logger.warning("PDF 解析需要 pymupdf: pip install pymupdf")
            return None
        except Exception as e:
            logger.warning(f"PDF 解析失败: {e}")
            return None

    def _parse_docx(self, data: bytes) -> str | None:
        """解析 DOCX 文件。"""
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)[:50000]
        except ImportError:
            logger.warning("DOCX 解析需要 python-docx: pip install python-docx")
            return None
        except Exception as e:
            logger.warning(f"DOCX 解析失败: {e}")
            return None
