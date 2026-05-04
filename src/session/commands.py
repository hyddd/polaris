"""System commands — slash commands handled without LLM overhead.

Commands:
  /new <name>     — Create new session
  /sessions       — List all sessions
  /session <id>   — Switch session (ID prefix or name match)
  /rename <name>  — Rename current session
  /reload         — Hot-reload config (API keys, model, etc.)
  /cleanup        — 手动触发数据清理/归档
  /reset          — Reset conversation memory
  /compact        — Manually trigger context compression
  /status         — Show session + token stats
  /help           — Show available commands
"""

from src.session.manager import SessionManager


def handle_command(text: str, session_mgr: SessionManager, channel: str = "") -> str | None:
    """Try to handle a system command. Returns response string, or None if not a command."""
    from src.core.context import get_channel as _ctx_channel
    channel = channel or _ctx_channel() or "default"

    text = text.strip()
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/reset":
        return _reset(session_mgr, channel)

    if cmd == "/compact":
        return _compact(session_mgr, channel)

    if cmd == "/status":
        return _status(session_mgr, channel)

    if cmd == "/help":
        return _help()

    if cmd == "/new":
        return _new(session_mgr, arg, channel)

    if cmd == "/sessions":
        return _list_sessions(session_mgr, channel)

    if cmd == "/session":
        return _switch(session_mgr, arg, channel)

    if cmd == "/rename":
        return _rename(session_mgr, arg, channel)

    if cmd == "/reload":
        return _reload()

    if cmd == "/cleanup":
        return _cleanup()

    return None


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


_WELCOME = (
    "\n\n你好！我是 Polaris，你的私人 AI 助手。我可以帮你：\n\n"
    "📅 **日程管理** — 「帮我建一个明天下午 3 点的会议」\n"
    "✅ **待办事项** — 「添加待办：买菜，优先级高」\n"
    "📝 **笔记管理** — 「记一下：Python 装饰器的用法」\n"
    "⏰ **定时提醒** — 「每天早上 9 点提醒我喝水」\n"
    "🔍 **联网搜索** — 「搜一下最新的 AI 新闻」\n"
    "🎭 **人格切换** — 「你来扮演诸葛亮」\n\n"
    "直接用自然语言告诉我你想做什么就好！"
)


def _new(session_mgr: SessionManager, arg: str, channel: str = "default") -> str:
    from src.core.config import config
    max_sessions = config.get("server.max_sessions", 10)
    if len(session_mgr._sessions) >= max_sessions:
        return (
            f"会话数已达上限（{max_sessions}），请先删除旧会话。\n"
            f"输入 /sessions 查看所有会话。"
        )
    name = arg.strip() if arg else ""
    session = session_mgr.create(name=name if name else None, source_channel=channel)
    summary = f"已创建会话「{session.name}」({session.session_id})。已切换到该会话。"
    if name:
        summary += f"\n提示：随时用 /session {session.session_id[:9]} 或 /session {name} 切回其他会话。"
    return summary + _WELCOME


def _list_sessions(session_mgr: SessionManager, channel: str = "default") -> str:
    sessions = session_mgr.list_sessions()
    active_session = session_mgr.active_session(channel)
    active_id = active_session.session_id

    lines = [f"当前活跃: 「{active_session.name}」({active_id})", "", "会话列表:"]
    for s in sessions:
        marker = "[活跃]" if s.session_id == active_id else "      "
        msg_count = s.metadata.get("message_count", 0)
        lines.append(f"{marker} {s.name} ({s.session_id}) — {msg_count}条消息 — 最后活跃 {_fmt_time(s.last_active)}")

    lines.append("")
    lines.append("输入 /session <id或名称> 切换会话。")
    return "\n".join(lines)


def _switch(session_mgr: SessionManager, arg: str, channel: str = "default") -> str:
    if not arg:
        return "用法: /session <会话ID或名称>。输入 /sessions 查看所有会话。"

    result = session_mgr.switch(arg, channel)
    if result:
        msg_count = result.metadata.get("message_count", 0)
        if msg_count > 0:
            extra = f"已有 {msg_count} 条消息"
            if result.compressor.summary:
                extra += f"，上次话题：{result.compressor.summary[:80]}"
        else:
            extra = "这是一个新会话。"
        return f"已切换到会话「{result.name}」({result.session_id})。{extra}"

    # No match — suggest sessions
    sessions = session_mgr.list_sessions()
    lines = [f"未找到匹配「{arg}」的会话。可选："]
    for s in sessions[:5]:
        lines.append(f"  /session {s.session_id} — {s.name}")
    return "\n".join(lines)


def _rename(session_mgr: SessionManager, arg: str, channel: str = "default") -> str:
    name = arg.strip()
    if not name:
        return "用法: /rename <新名称>"
    active_session = session_mgr.active_session(channel)
    session_mgr.rename(active_session.session_id, name)
    return f"会话已重命名为「{name}」"


def _reset(session_mgr: SessionManager, channel: str = "default") -> str:
    session_mgr.reset_active(channel)
    return "已重置对话记忆。所有上下文已清除，让我们重新开始。" + _WELCOME


def _compact(session_mgr: SessionManager, channel: str = "default") -> str:
    session = session_mgr.active_session(channel)
    messages = session.memory.get_history()
    if not messages:
        return "当前没有对话内容需要压缩。"

    compressor = session.compressor
    summary, recent = compressor.process(list(messages))

    session.memory.clear_messages()
    for msg in recent:
        session.memory.add_message(msg)

    before = len(messages)
    after = len(recent)
    return (
        f"上下文已压缩。\n"
        f"• 消息数: {before} → {after}\n"
        f"• 摘要长度: {len(summary)} 字符\n"
        f"• 节省约 {max(0, before - after)} 条消息"
    )


def _status(session_mgr: SessionManager, channel: str = "default") -> str:
    session = session_mgr.active_session(channel)
    messages = session.memory.get_history()
    compressor = session.compressor

    used = compressor.estimate_total_tokens(messages) if messages else 0
    model_max = compressor.model_max_context
    pct = (used / model_max * 100) if model_max else 0

    user_msgs = sum(1 for m in messages if m.type == "human")
    ai_msgs = sum(1 for m in messages if m.type == "ai")

    lines = [
        f"📊 「{session.name}」会话状态",
        "",
        f"• 消息: {len(messages)} (用户:{user_msgs} AI:{ai_msgs})",
        f"• Token: {used:,} / {model_max:,} ({pct:.1f}%)",
        f"• 压缩摘要: {'已生成' if compressor.summary else '暂无'}",
        "",
        f"• ID: {session.session_id}",
        f"• 总会话数: {len(session_mgr._sessions)}",
    ]

    return "\n".join(lines)


def _reload() -> str:
    """Re-read YAML config files and publish config:reload event."""
    try:
        from src.core.config import config
        config.reload()

        lines = ["配置已重载。"]
        llm_model = config.get("llm.model", "gpt-4o")
        llm_base_url = config.get("llm.base_url", "https://api.openai.com/v1")
        api_key = config.get("llm.api_key", "")
        lines.append(f"• LLM_MODEL: {llm_model}")
        lines.append(f"• LLM_BASE_URL: {llm_base_url}")
        lines.append(f"• API_KEY: {'已设置' if api_key else '未设置'}")

        return "\n".join(lines)
    except Exception as e:
        return f"配置重载失败：{e}"


def _cleanup() -> str:
    try:
        from src.core.events import event_bus
        event_bus.publish("cleanup:now")
        return "已触发数据清理，各模块正在处理。"
    except Exception as e:
        return f"数据清理失败：{e}"


def _help() -> str:
    return (
        "📋 **可用命令：**\n\n"
        "/new <名称> — 创建新会话\n"
        "/sessions — 查看所有会话\n"
        "/session <id|名称> — 切换会话\n"
        "/rename <名称> — 重命名当前会话\n"
        "/status — 会话状态\n"
        "/compact — 压缩上下文\n"
        "/reset — 重置会话记忆\n"
        "/reload — 热重载配置\n"
        "/cleanup — 清理过期数据\n\n"
        "💡 **使用技巧：**\n"
        "- 直接用自然语言描述需求即可\n"
        "- 说「你是诸葛亮」可以切换人设\n"
        "- 说「搜索 xxx」可以联网查询\n"
        "- 说「提醒我 xxx」可以创建定时提醒"
    )


def _fmt_time(iso_str: str) -> str:
    if not iso_str:
        return "未知"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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
