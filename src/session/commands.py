"""System commands — slash commands handled without LLM overhead.

Commands:
  /new <name>     — Create new session
  /sessions       — List all sessions
  /session <id>   — Switch session (ID prefix or name match)
  /rename <name>  — Rename current session
  /reload         — Hot-reload config from .env (API keys, model, etc.)
  /reset          — Reset conversation memory
  /compact        — Manually trigger context compression
  /status         — Show session + token stats
  /help           — Show available commands
"""

from src.session.manager import SessionManager


def handle_command(text: str, session_mgr: SessionManager, channel: str = "") -> str | None:
    """Try to handle a system command. Returns response string, or None if not a command."""
    from src.context import get_channel as _ctx_channel
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

    return None


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


def _new(session_mgr: SessionManager, arg: str, channel: str = "default") -> str:
    name = arg.strip() if arg else ""
    session = session_mgr.create(name=name if name else None, source_channel=channel)
    summary = f"已创建会话「{session.name}」({session.session_id})。已切换到该会话。"
    if name:
        summary += f"\n提示：随时用 /session {session.session_id[:9]} 或 /session {name} 切回其他会话。"
    return summary


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
    return "已重置对话记忆。所有上下文已清除，让我们重新开始。"


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
    import json
    from datetime import date
    from src.agent.executor import UNIFIED_SYSTEM_PROMPT, _format_persona
    from src.tools.registry import ToolRegistry

    session = session_mgr.active_session(channel)
    messages = session.memory.get_history()
    compressor = session.compressor
    summary = compressor.summary

    # system prompt = 日期 + 人设 + 摘要 + 行为准则
    today = date.today().isoformat()
    persona_text = _format_persona(session.persona)
    system_parts = [f"今天是 {today}。"]
    if persona_text:
        system_parts.append(persona_text)
    if summary:
        system_parts.append(summary)
    system_parts.append(UNIFIED_SYSTEM_PROMPT)
    system_tokens = compressor._count_tokens_str("\n\n".join(system_parts))

    # 工具定义 token
    tools = ToolRegistry.get_instance().list_tools()
    tool_schemas = [t.args_schema.model_json_schema() if hasattr(t, 'args_schema') and t.args_schema else {} for t in tools]
    tool_text = json.dumps(tool_schemas, ensure_ascii=False)
    tool_tokens = compressor._count_tokens_str(tool_text)

    # 消息 + system prompt + 工具 = LLM 实际上下文
    message_tokens = compressor._count_tokens(messages)
    used = system_tokens + message_tokens + tool_tokens
    model_max = compressor.model_max_context
    pct = (used / model_max * 100) if model_max else 0

    user_msgs = sum(1 for m in messages if m.type == "human")
    ai_msgs = sum(1 for m in messages if m.type == "ai")

    lines = [
        f"📊 「{session.name}」会话状态",
        "",
        f"• 消息: {len(messages)} (用户:{user_msgs} AI:{ai_msgs})",
        f"• Token: {used:,} / {model_max:,} ({pct:.1f}%)",
        "",
        f"• ID: {session.session_id}",
        f"• 总会话数: {len(session_mgr._sessions)}",
    ]

    return "\n".join(lines)


def _reload() -> str:
    """Re-read .env and trigger config reload event."""
    try:
        from src.config import config
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


def _help() -> str:
    return """**Polaris 个人效率助手**

🛠 **系统指令**
`/new <名称>` — 创建新会话
`/sessions` — 查看所有会话
`/session <id|名称>` — 切换会话
`/rename <名称>` — 重命名当前会话
`/reload` — 热重载配置（LLM + 通道凭证，无需重启）
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
