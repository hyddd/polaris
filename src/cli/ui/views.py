"""结构化查询结果的展示（REPL 与单次命令共用）。"""
from datetime import datetime, timezone

from src.cli.ui.render import Renderer


def relative_time(iso: str | None, now: datetime | None = None) -> str:
    if not iso:
        return "-"
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return "-"
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    secs = int(((now or datetime.now(timezone.utc)) - t).total_seconds())
    if secs < 60:
        return "刚刚"
    for unit, size in (("天", 86400), ("小时", 3600), ("分钟", 60)):
        if secs >= size:
            return f"{secs // size} {unit}前"
    return "-"


STATUS_LABELS = {
    "todo": {"pending": "待办", "in_progress": "进行中", "done": "已完成"},
    "reminder": {"active": "活跃", "paused": "已暂停", "cancelled": "已完成", "failed": "未送达"},
}
PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
REPEAT_LABELS = {"none": "一次", "daily": "每天", "weekly": "每周", "monthly": "每月"}
SCOPE_LABELS = {"public": "【公共】", "private": "【私人】"}


def _scope(item: dict) -> str:
    return SCOPE_LABELS.get(item.get("scope"), "【私人】")


def show_todos(r: Renderer, items: list[dict]) -> None:
    if not items:
        r.dim("（没有待办）")
        return
    rows = [[t.get("id", ""), _scope(t), STATUS_LABELS["todo"].get(t.get("status"), t.get("status", "")),
             PRIORITY_LABELS.get(t.get("priority"), t.get("priority", "")), t.get("due") or "-",
             t.get("title", "")] for t in items]
    r.table(["ID", "范围", "状态", "优先级", "截止", "标题"], rows)


def show_calendar(r: Renderer, items: list[dict]) -> None:
    if not items:
        r.dim("（没有日程）")
        return
    rows = [[e.get("id", ""), _scope(e), e.get("date", ""), e.get("time", ""), f"{e.get('duration', '')} 分钟",
             e.get("title", ""), "、".join(e.get("attendees") or [])] for e in items]
    r.table(["ID", "范围", "日期", "时间", "时长", "标题", "参与人"], rows)


def show_reminders(r: Renderer, items: list[dict]) -> None:
    if not items:
        r.dim("（没有提醒）")
        return
    rows = [[x.get("id", ""), _scope(x), x.get("trigger_time", "").replace("T", " ")[:16],
             REPEAT_LABELS.get(x.get("repeat_rule"), x.get("repeat_rule", "")),
             STATUS_LABELS["reminder"].get(x.get("status"), x.get("status", "")),
             x.get("title", "")] for x in items]
    r.table(["ID", "范围", "时间", "重复", "状态", "标题"], rows)


def show_sessions(r: Renderer, sessions: list[dict], current: str | None = None, numbered: bool = False) -> None:
    if not sessions:
        r.dim("（没有会话）")
        return
    rows = []
    for i, s in enumerate(sessions, 1):
        mark = "●" if s["session_id"] == current else ""
        row = [mark, s["name"], f"{s.get('message_count', 0)} 条", relative_time(s.get("last_active")), s["session_id"]]
        rows.append(([str(i)] if numbered else []) + row)
    cols = (["#"] if numbered else []) + ["", "名称", "消息", "最近活跃", "ID"]
    r.table(cols, rows)


def show_history(r: Renderer, messages: list[dict], limit: int | None = None, compacted: bool = False) -> None:
    """显示会话消息（用户与助手的文字，跳过工具中间消息），样式和实时对话一致。

    limit=None 显示全部（恢复会话时，和 Claude Code 一样整段加载）。
    compacted：会话做过上下文压缩，更早的内容只剩摘要，先显示一行"对话已压缩"。
    """
    visible = [m for m in messages if m.get("type") in ("human", "ai") and _text(m.get("content"))]
    if compacted:
        r.dim("  ─── 对话已压缩：更早的内容已总结成摘要，以下是之后的消息 ───")
        r.blank()
    if limit is not None and len(visible) > limit:
        r.dim(f"  …更早的 {len(visible) - limit} 条已省略（/history 50 可看更多）")
        visible = visible[-limit:]
    for m in visible:
        if m["type"] == "human":
            r.user_echo(_text(m["content"]))
        else:
            r.message(_text(m["content"]))
        r.blank()


def _text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):   # 多模态消息：只取文字部分
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text").strip()
    return ""
