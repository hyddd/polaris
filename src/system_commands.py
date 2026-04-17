"""System commands — slash commands handled without LLM overhead.

Commands:
  /new <name>     — Create new session
  /sessions       — List all sessions
  /session <id>   — Switch session (ID prefix or name match)
  /rename <name>  — Rename current session
  /reset          — Reset conversation memory
  /compact        — Manually trigger context compression
  /status         — Show session + token stats
  /help           — Show available commands
"""

from src.session_manager import SessionManager


def handle_command(text: str, session_mgr: SessionManager) -> str | None:
    """Try to handle a system command. Returns response string, or None if not a command."""
    text = text.strip()
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/reset":
        return _reset(session_mgr)

    if cmd == "/compact":
        return _compact(session_mgr)

    if cmd == "/status":
        return _status(session_mgr)

    if cmd == "/help":
        return _help()

    if cmd == "/new":
        return _new(session_mgr, arg)

    if cmd == "/sessions":
        return _list_sessions(session_mgr)

    if cmd == "/session":
        return _switch(session_mgr, arg)

    if cmd == "/rename":
        return _rename(session_mgr, arg)

    return None


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


def _new(session_mgr: SessionManager, name: str) -> str:
    name = name.strip() if name else ""
    session = session_mgr.create(name=name if name else None, source_channel="command")
    summary = f"已创建会话「{session.name}」({session.session_id})。已切换到该会话。"
    if name:
        summary += f"\n提示：随时用 /session {session.session_id[:9]} 或 /session {name} 切回其他会话。"
    return summary


def _list_sessions(session_mgr: SessionManager) -> str:
    sessions = session_mgr.list_sessions()
    active_id = session_mgr._active_id

    lines = [f"当前活跃: 「{session_mgr.active_session.name}」({active_id})", "", "会话列表:"]
    for s in sessions:
        marker = "[活跃]" if s.session_id == active_id else "      "
        msg_count = s.metadata.get("message_count", 0)
        lines.append(f"{marker} {s.name} ({s.session_id}) — {msg_count}条消息 — 最后活跃 {_fmt_time(s.last_active)}")

    lines.append("")
    lines.append("输入 /session <id或名称> 切换会话。")
    return "\n".join(lines)


def _switch(session_mgr: SessionManager, arg: str) -> str:
    if not arg:
        return "用法: /session <会话ID或名称>。输入 /sessions 查看所有会话。"

    result = session_mgr.switch(arg)
    if result:
        summary = result.compressor.summary
        extra = f"上次话题：{summary[:100]}" if summary else "这是一个新会话。"
        return f"已切换到会话「{result.name}」({result.session_id})。{extra}"

    # No match — suggest sessions
    sessions = session_mgr.list_sessions()
    lines = [f"未找到匹配「{arg}」的会话。可选："]
    for s in sessions[:5]:
        lines.append(f"  /session {s.session_id} — {s.name}")
    return "\n".join(lines)


def _rename(session_mgr: SessionManager, name: str) -> str:
    if not name.strip():
        return "用法: /rename <新名称>"
    session_mgr.rename(session_mgr._active_id, name.strip())
    return f"会话已重命名为「{name.strip()}」"


def _reset(session_mgr: SessionManager) -> str:
    session_mgr.reset_active()
    return "已重置对话记忆。所有上下文已清除，让我们重新开始。"


def _compact(session_mgr: SessionManager) -> str:
    session = session_mgr.active_session
    messages = session.memory.get_history()
    if not messages:
        return "当前没有对话内容需要压缩。"

    compressor = session.compressor
    summary, recent = compressor.process(list(messages))

    session.memory._messages.clear()
    for msg in recent:
        session.memory._messages.append(msg)

    before = len(messages)
    after = len(recent)
    return (
        f"上下文已压缩。\n"
        f"• 消息数: {before} → {after}\n"
        f"• 摘要长度: {len(summary)} 字符\n"
        f"• 节省约 {max(0, before - after)} 条消息"
    )


def _status(session_mgr: SessionManager) -> str:
    session = session_mgr.active_session
    messages = session.memory.get_history()
    compressor = session.compressor
    summary = compressor.summary

    total_tokens = compressor._count_tokens(messages)
    summary_tokens = compressor._summary_tokens
    budget = compressor.compress_trigger
    model_max = compressor.model_max_context

    user_msgs = sum(1 for m in messages if m.type == "human")
    ai_msgs = sum(1 for m in messages if m.type == "ai")
    tool_msgs = sum(1 for m in messages if m.type == "tool")

    lines = [
        f"📊 「{session.name}」会话状态",
        "",
        "**消息统计**",
        f"• 总消息数: {len(messages)} (用户:{user_msgs} AI:{ai_msgs} 工具:{tool_msgs})",
        f"• 最近消息 token: {total_tokens}",
        f"• 摘要长度: {len(summary)} 字符 (~{summary_tokens} tokens)",
        "",
        "**Token 预算**",
        f"• 模型最大窗口: {model_max:,}",
        f"• 压缩触发线: {budget:,} ({(budget/model_max)*100:.0f}%)",
        f"• 当前占用率: {((total_tokens + summary_tokens) / model_max * 100):.1f}%",
        "",
        "**会话管理**",
        f"• 会话 ID: {session.session_id}",
        f"• 总会话数: {len(session_mgr._sessions)}",
    ]

    return "\n".join(lines)


def _help() -> str:
    return """**Polaris 个人效率助手**

🛠 **系统指令**
`/new <名称>` — 创建新会话
`/sessions` — 查看所有会话
`/session <id|名称>` — 切换会话
`/rename <名称>` — 重命名当前会话
`/reset` — 重置当前会话记忆
`/compact` — 手动压缩上下文
`/status` — 查看会话状态
`/help` — 显示此帮助

💬 **自然语言能力**
• **查看日程** —「今天有什么安排」
• **会议准备** —「下午3点的会帮我准备」
• **搜索笔记** —「上次RBAC讨论了什么」
• **快速记录** —「记一下，明天下午开会」
• **管理信息** —「取消明天的晨会」

直接说人话就行，不用记指令。"""


def _fmt_time(iso_str: str) -> str:
    if not iso_str:
        return "未知"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = now - dt
        if diff.total_seconds() < 60:
            return "刚才"
        if diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() / 60)}分钟前"
        if diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}小时前"
        if diff.days == 1:
            return "昨天"
        return f"{diff.days}天前"
    except Exception:
        return iso_str[:10]
