"""Conversation compressor — token-aware memory with LLM summarization.

Two-layer memory:
  1. Summary layer: compressed conversation history, injected into system prompt
  2. Recent messages layer: last N messages kept verbatim, with token budget trimming
"""

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

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


class ConversationCompressor:
    def __init__(self, max_recent: int = 8, max_history_tokens: int = 4000):
        self.summary = ""
        self.max_recent = max_recent
        self.max_history_tokens = max_history_tokens

    def process(self, messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
        """Process messages: compress overflow into summary, trim to budget.

        Returns (summary, trimmed_recent_messages).
        """
        if not messages:
            return self.summary, []

        # Compress overflow into summary
        if len(messages) > self.max_recent:
            overflow = messages[:-self.max_recent]
            recent = messages[-self.max_recent:]
            self.summary = self._summarize(self.summary, overflow)
        else:
            recent = list(messages)

        # Trim recent messages to token budget
        recent = self._trim_to_budget(recent)

        return self.summary, recent

    def _summarize(self, existing: str, new_messages: list[BaseMessage]) -> str:
        """Call LLM to merge new messages into running summary."""
        new_text = self._messages_to_text(new_messages)

        try:
            llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
            prompt = SUMMARIZE_PROMPT.format(existing=existing or "无", new_messages=new_text)
            result = llm.invoke([HumanMessage(content=prompt)])
            return result.content.strip()
        except Exception:
            # Fallback: simple concatenation
            if existing:
                return f"{existing}\n{new_text[:200]}"
            return new_text[:300]

    def _trim_to_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Trim messages from oldest until within token budget."""
        if not messages:
            return []

        total = self._estimate_tokens(messages)
        if total <= self.max_history_tokens:
            return list(messages)

        # Always keep the last message (current user input)
        kept = [messages[-1]]
        remaining_budget = self.max_history_tokens - self._estimate_tokens(kept)

        # Work backwards, keeping messages that fit
        for msg in reversed(messages[:-1]):
            msg_tokens = self._estimate_tokens([msg])
            if remaining_budget >= msg_tokens:
                kept.insert(0, msg)
                remaining_budget -= msg_tokens
            else:
                break

        return kept

    def _estimate_tokens(self, messages: list[BaseMessage]) -> int:
        """Rough token estimation: chars/2 for Chinese, chars/4 for English."""
        total = 0
        for msg in messages:
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, str):
                # Chinese chars ≈ 1 token, English ≈ 0.25 token per char
                # Rough: total_chars / 2
                total += max(1, len(content) // 2)
            else:
                total += 10  # Non-string content placeholder
        return total

    def _messages_to_text(self, messages: list[BaseMessage]) -> str:
        """Convert messages to readable text for summarization."""
        lines = []
        for msg in messages:
            role = "用户" if msg.type == "human" else "助手" if msg.type == "ai" else "系统"
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, str) and content:
                lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)
