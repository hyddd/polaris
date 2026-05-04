"""TextChunker — 文本分块器，为知识库做准备。"""

import logging
import re

logger = logging.getLogger("polaris.rag.chunker")


class TextChunker:
    """按段落优先、固定大小兜底的策略分块。"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: dict | None = None) -> list[dict]:
        """将文本分块，返回 [{"content": str, "metadata": dict}, ...]。

        策略：
        1. 按段落（空行）分割
        2. 短段落合并，直到接近 chunk_size
        3. 超长段落按 chunk_size + overlap 切分
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        paragraphs = re.split(r"\n\s*\n", text.strip())
        chunks: list[dict] = []
        buffer = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 超长段落：先 flush buffer，再切分段落本身
            if len(para) > self.chunk_size:
                if buffer:
                    chunks.append(self._make_chunk(buffer, metadata))
                    buffer = ""
                chunks.extend(self._split_long(para, metadata))
                continue

            # 合并短段落
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para
            if len(candidate) > self.chunk_size and buffer:
                chunks.append(self._make_chunk(buffer, metadata))
                buffer = para
            else:
                buffer = candidate

        if buffer:
            chunks.append(self._make_chunk(buffer, metadata))

        logger.debug(f"分块完成: {len(chunks)} 块, 原文 {len(text)} 字符")
        return chunks

    def _split_long(self, text: str, metadata: dict) -> list[dict]:
        """按 chunk_size + overlap 切分超长文本。"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            segment = text[start:end]
            chunks.append(self._make_chunk(segment, metadata))
            start += self.chunk_size - self.overlap
        return chunks

    def _make_chunk(self, content: str, metadata: dict) -> dict:
        return {"content": content, "metadata": dict(metadata)}
