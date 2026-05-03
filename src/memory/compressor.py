"""Conversation compressor — token-budget-aware memory with LLM summarization.

Two-layer memory:
  1. Summary layer: compressed conversation history, injected into system prompt
  2. Recent messages layer: recent messages kept verbatim

Compression triggers when total context tokens exceed model_max_context * threshold,
NOT based on message count. Large-context models (200k) rarely compress.
"""

import os
from langchain_core.messages import BaseMessage, HumanMessage
from src.llm.openai import create_chat_model
import src.config as _cfg  # Read at call time for hot-reload support

SUMMARIZE_PROMPT = """请将以下新对话内容合并到已有摘要中，生成更新后的摘要。

要求：
- 2-4 句话，中文
- 包含：用户身份信息、重要讨论主题、已执行的工具操作和结果
- 保留关键事实和数据，忽略闲聊寒暄
- 如果已有摘要和新内容无关，保留已有摘要并追加新内容

已有摘要：{existing}

新对话内容：
{new_messages}

请输出更新后的摘要（不要包含任何其他内容）："""

# Reserve tokens for system prompt, tool definitions, and model response
RESERVE_TOKENS = 8000


class ConversationCompressor:
    def __init__(self, model_max_context: int = 200000, compression_threshold: float = 0.8):
        self.model_max_context = model_max_context
        self.compress_trigger = int(model_max_context * compression_threshold)
        self.summary = ""
        self._summary_tokens = 0

    def process(self, messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
        """Process messages. Only compresses when total tokens exceed trigger.

        Returns (summary, recent_messages).
        """
        if not messages:
            return self.summary, []

        total_tokens = self._count_tokens(messages) + self._summary_tokens + RESERVE_TOKENS

        if total_tokens <= self.compress_trigger:
            return self.summary, list(messages)

        # Need compression: take oldest messages until we're under budget
        target_tokens = self.compress_trigger - RESERVE_TOKENS - self._summary_tokens
        split_at = self._find_split_point(messages, target_tokens)

        if split_at > 0:
            overflow = messages[:split_at]
            recent = messages[split_at:]
            self.summary = self._summarize(self.summary, overflow)
            self._summary_tokens = self._count_tokens_str(self.summary)
        else:
            recent = list(messages)

        # Final safety trim: if still over budget, trim from oldest
        while recent and self._count_tokens(recent) + self._summary_tokens + RESERVE_TOKENS > self.compress_trigger:
            # Move one more message from recent to summary
            self.summary = self._summarize(self.summary, [recent.pop(0)])
            self._summary_tokens = self._count_tokens_str(self.summary)

        return self.summary, recent

    def _find_split_point(self, messages: list[BaseMessage], target_tokens: int) -> int:
        """Find index where messages should be split: keep last N that fit in target."""
        kept_tokens = 0
        for i in range(len(messages) - 1, -1, -1):
            kept_tokens += self._count_tokens([messages[i]])
            if kept_tokens > target_tokens:
                return i + 1
        return 0

    def _summarize(self, existing: str, new_messages: list[BaseMessage]) -> str:
        """Call LLM to merge new messages into running summary."""
        new_text = self._messages_to_text(new_messages)

        try:
            llm = create_chat_model(temperature=0)
            prompt = SUMMARIZE_PROMPT.format(existing=existing or "无", new_messages=new_text)
            result = llm.invoke([HumanMessage(content=prompt)])
            return result.content.strip()
        except Exception:
            if existing:
                return f"{existing}\n{new_text[:200]}"
            return new_text[:300]

    def _count_tokens(self, messages: list[BaseMessage]) -> int:
        """Count tokens across messages. Uses tiktoken if available, else char-based estimate."""
        total = 0
        for msg in messages:
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, str):
                total += self._count_tokens_str(content)
            elif isinstance(content, list):
                # Multi-modal content blocks
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += self._count_tokens_str(block["text"])
            else:
                total += 4
        return total

    def _count_tokens_str(self, text: str) -> int:
        """Token count for a string. Uses tiktoken if available, else char/2."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except (ImportError, Exception):
            # Rough: Chinese ≈ 1 tok/char, English ≈ 0.25 tok/char, avg ≈ 0.5
            return max(1, len(text) // 2)

    def _messages_to_text(self, messages: list[BaseMessage]) -> str:
        lines = []
        for msg in messages:
            role = "用户" if msg.type == "human" else "助手" if msg.type == "ai" else "系统"
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, str) and content:
                lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)
