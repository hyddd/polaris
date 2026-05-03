"""ChannelPlugin abstract base class."""

import abc
import logging

logger = logging.getLogger("polaris.channels")


class ChannelPlugin(abc.ABC):
    """Base class for chat channel integrations (Feishu, QQ, WeChat, etc.)."""

    @staticmethod
    def _split_message(text: str, max_length: int) -> list[str]:
        """按段落/句子边界智能分段，fallback 到硬截断。

        优先按段落（\\n\\n）边界拆分，其次按句子（。！？）边界拆分，
        若无可用的自然边界则按字符数硬截断。
        """
        if not text:
            return []
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            chunk = remaining[:max_length]

            # 1. 按段落边界（\\n\\n）
            split_pos = chunk.rfind('\n\n')
            if split_pos > 0:
                chunks.append(remaining[:split_pos])
                remaining = remaining[split_pos:].lstrip('\n')
                continue

            # 2. 按句子边界（。！？）
            split_pos = -1
            for p in ('。', '！', '？'):
                pos = chunk.rfind(p)
                if pos > split_pos:
                    split_pos = pos
            if split_pos > 0:
                chunks.append(remaining[:split_pos + 1])
                remaining = remaining[split_pos + 1:]
                continue

            # 3. 硬截断
            chunks.append(chunk)
            remaining = remaining[max_length:]

        return chunks

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Channel name, e.g. 'feishu', 'qq'."""
        ...

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Check if this channel has the required credentials/config."""
        ...

    @abc.abstractmethod
    def start(self) -> None:
        """Start the channel (usually a blocking call — runs in a daemon thread)."""
        ...

    def send_message(self, session_id: str, message: str) -> bool:
        """发送消息到指定会话。返回是否成功。"""
        raise NotImplementedError(f"{self.name} 不支持主动发送消息")

    def stop(self) -> None:
        """Optional: clean shutdown."""
        pass

    def get_credentials(self) -> dict:
        """Return current credentials for change detection. Override in subclass."""
        return {}
