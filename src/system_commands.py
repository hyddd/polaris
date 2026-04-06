"""System commands — slash commands handled without LLM overhead.

Commands:
  /reset   — Reset conversation memory
  /compact — Manually trigger context compression
  /status  — Show current context stats
  /help    — Show available commands and capabilities
"""

from langchain_core.messages import BaseMessage
from src.memory.store import MemoryManager
from src.memory.compressor import ConversationCompressor


def handle_command(text: str, memory: MemoryManager, compressor: ConversationCompressor) -> str | None:
    """Try to handle a system command. Returns response string, or None if not a command."""
    text = text.strip()

    if text == "/reset":
        return _reset(memory, compressor)

    if text == "/compact":
        return _compact(memory, compressor)

    if text == "/status":
        return _status(memory, compressor)

    if text == "/help":
        return _help()

    return None


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


def _reset(memory: MemoryManager, compressor: ConversationCompressor) -> str:
    memory._messages.clear()
    compressor.summary = ""
    compressor._summary_tokens = 0
    return "已重置对话记忆。所有上下文已清除，让我们重新开始。"


def _compact(memory: MemoryManager, compressor: ConversationCompressor) -> str:
    messages = memory.get_history()
    if not messages:
        return "当前没有对话内容需要压缩。"

    summary, recent = compressor.process(list(messages))

    # Replace memory messages with just the compressed recent
    memory._messages.clear()
    for msg in recent:
        memory._messages.append(msg)

    before = len(messages)
    after = len(recent)
    summary_len = len(summary)
    return (
        f"上下文已压缩。\n"
        f"• 消息数: {before} → {after}\n"
        f"• 摘要长度: {summary_len} 字符\n"
        f"• 节省约 {max(0, before - after)} 条消息"
    )


def _status(memory: MemoryManager, compressor: ConversationCompressor) -> str:
    messages = memory.get_history()
    summary = compressor.summary

    # Token counts
    total_tokens = compressor._count_tokens(messages)
    summary_tokens = compressor._summary_tokens
    budget = compressor.compress_trigger
    model_max = compressor.model_max_context

    user_msgs = sum(1 for m in messages if m.type == "human")
    ai_msgs = sum(1 for m in messages if m.type == "ai")
    tool_msgs = sum(1 for m in messages if m.type == "tool")

    lines = [
        "📊 **当前上下文状态**",
        "",
        f"**消息统计**",
        f"• 总消息数: {len(messages)} (用户:{user_msgs} AI:{ai_msgs} 工具:{tool_msgs})",
        f"• 最近消息 token: {total_tokens}",
        f"• 摘要长度: {len(summary)} 字符 (~{summary_tokens} tokens)",
        "",
        f"**Token 预算**",
        f"• 模型最大窗口: {model_max:,}",
        f"• 压缩触发线: {budget:,} ({(budget/model_max)*100:.0f}%)",
        f"• 当前占用率: {((total_tokens + summary_tokens) / model_max * 100):.1f}%",
        f"• 下一次压缩: 约需 {(budget - total_tokens - summary_tokens):,} tokens",
    ]

    return "\n".join(lines)


def _help() -> str:
    return """**Polaris 个人效率助手**

🛠 **系统指令**
`/reset` — 重置对话记忆
`/compact` — 手动压缩上下文
`/status` — 查看上下文状态
`/help` — 显示此帮助

💬 **自然语言能力**
• **查看日程** —「今天有什么安排」
• **会议准备** —「下午3点的会帮我准备」
• **搜索笔记** —「上次RBAC讨论了什么」
• **快速记录** —「记一下，明天下午开会」
• **管理信息** —「取消明天的晨会」

直接说人话就行，不用记指令。"""
