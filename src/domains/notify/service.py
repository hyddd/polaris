"""通知发送：主动通知（接口 / 网页 / AI 工具）和提醒到点转发共用。

- 企业微信走群机器人 webhook；QQ / 飞书走已启用的渠道插件（渠道没启用或没连上时该目标失败）；
- 每个目标每分钟最多 RATE_LIMIT 条（与企业微信群机器人的官方上限一致），主动通知和提醒转发合计；
- 失败不重试：主动通知把每个目标的结果返回给调用方；提醒转发只写日志，不影响提醒原有的送达方式。
"""
import logging
import threading
import time
from collections import defaultdict, deque

from .targets import Target, configured_targets
from .webhook import send_markdown

logger = logging.getLogger("polaris.notify")

RATE_LIMIT = 20                  # 每个目标每分钟最多发送条数
TITLE_LIMIT = 200
CONTENT_LIMIT = 4000
SCOPE_LABELS = {"public": "公共", "private": "私人"}


class NotifyError(Exception):
    """调用参数有误（目标不存在、内容为空或过长）。message 面向用户。"""


class _RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window: float = 60.0):
        self.limit, self.window = limit, window
        self._sent: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, name: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._sent[name]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._sent.clear()


rate_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# 发送到单个目标
# ---------------------------------------------------------------------------

def _channel_plugin(name: str):
    from src.core.channel.loader import get_discovered_channels
    return next((c for c in get_discovered_channels() if c.name == name), None)


def availability(target: Target) -> tuple[bool, str]:
    """目标当前能否发送（不发消息）。"""
    if target.type == "wecom":
        return True, ""
    plugin = _channel_plugin(target.plugin)
    if plugin is None:
        return False, f"{'QQ' if target.plugin == 'qq' else '飞书'}渠道未启用（channels.{target.plugin}.enabled）"
    if not plugin.is_configured():
        return False, f"{'QQ' if target.plugin == 'qq' else '飞书'}渠道未配置凭据"
    return True, ""


def deliver(target: Target, markdown: str, text: str, transport=None) -> tuple[bool, str]:
    """发送到一个目标：企业微信用 markdown，QQ / 飞书用纯文本。返回 (是否成功, 失败原因)。"""
    if not rate_limiter.acquire(target.name):
        return False, f"超过频率限制（每个目标每分钟最多 {RATE_LIMIT} 条）"
    if target.type == "wecom":
        return send_markdown(target.url, target.name, markdown, transport)
    ok, reason = availability(target)
    if not ok:
        return False, reason
    plugin = _channel_plugin(target.plugin)
    try:
        if target.type == "feishu-chat":
            sent = plugin.send_message(session_id=target.address, message=text, channel="")
        else:
            sent = plugin.send_message(session_id="", message=text, channel=target.channel)
    except Exception as e:
        logger.warning(f"通知发送异常（{target.name}）：{e}")
        return False, f"发送异常：{e}"
    return (True, "") if sent else (False, "渠道未连接或发送失败，详见服务日志")


# ---------------------------------------------------------------------------
# 主动通知
# ---------------------------------------------------------------------------

def list_targets() -> list[dict]:
    targets, _ = configured_targets()
    out = []
    for t in targets:
        ok, reason = availability(t)
        out.append({**t.public_dict(), "available": ok, **({"reason": reason} if reason else {})})
    return out


def _footer(source: str) -> str:
    from src.core.db import instance_name
    return f"来自：{source or '未注明'} · {instance_name()}"


def send_notification(target_names: list[str], title: str = "", content: str = "",
                      source: str = "", transport=None) -> list[dict]:
    """按目标名称发送一条通知，返回每个目标的结果 [{"target", "ok", "error"?}]。参数有误时抛 NotifyError。"""
    title, content = (title or "").strip(), (content or "").strip()
    if not title and not content:
        raise NotifyError("标题和正文不能都为空")
    if len(title) > TITLE_LIMIT:
        raise NotifyError(f"标题最多 {TITLE_LIMIT} 字")
    if len(content) > CONTENT_LIMIT:
        raise NotifyError(f"正文最多 {CONTENT_LIMIT} 字")
    names = list(dict.fromkeys(n.strip() for n in (target_names or []) if n and n.strip()))
    if not names:
        raise NotifyError("至少指定一个通知目标")
    targets, _ = configured_targets()
    by_name = {t.name: t for t in targets}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        known = "、".join(by_name) or "（未配置任何目标）"
        raise NotifyError(f"通知目标不存在：{'、'.join(unknown)}。可用目标：{known}")

    footer = _footer(source)
    markdown = "\n".join(x for x in (f"📢 **{title}**" if title else "", content, f"> {footer}") if x)
    text = "\n".join(x for x in (f"📢 {title}" if title else "", content, f"—— {footer}") if x)
    results = []
    for name in names:
        ok, error = deliver(by_name[name], markdown, text, transport)
        results.append({"target": name, "ok": ok, **({"error": error} if error else {})})
    sent = [r["target"] for r in results if r["ok"]]
    logger.info(f"主动通知（{source or '未注明'}）：{title or content[:30]} → 成功 {sent or '无'}，"
                f"失败 {[r['target'] for r in results if not r['ok']] or '无'}")
    return results


# ---------------------------------------------------------------------------
# 提醒到点转发
# ---------------------------------------------------------------------------

def _reminder_messages(reminder: dict) -> tuple[str, str]:
    from src.core.db import instance_name
    scope = reminder.get("scope") or "private"
    label = SCOPE_LABELS.get(scope, scope)
    when = str(reminder.get("trigger_time") or "").replace("T", " ")[:16]
    title, desc = reminder.get("title", ""), reminder.get("description")
    color = "info" if scope == "public" else "comment"
    md = [f"⏰ **提醒：{title}**"] + ([f"> {desc}"] if desc else []) + ([f"> 时间：{when}"] if when else [])
    md += [f'> 范围：<font color="{color}">{label}</font>', f"> 来自：{instance_name()}"]
    tx = [f"⏰ 提醒：{title}"] + ([desc] if desc else []) + ([f"时间：{when}"] if when else [])
    tx += [f"范围：{label}", f"来自：{instance_name()}"]
    return "\n".join(md), "\n".join(tx)


def forward_reminder(reminder: dict, transport=None, background: bool = True) -> list[str]:
    """提醒到点：转发给 scopes 匹配的所有目标（企业微信、QQ、飞书），返回目标名称。每次现读配置。"""
    targets, problems = configured_targets()
    for p in problems:
        logger.warning(f"配置提示：{p}，已跳过")
    scope = reminder.get("scope") or "private"
    matched = [t for t in targets if scope in t.scopes]
    if not matched:
        return []
    markdown, text = _reminder_messages(reminder)

    def _run():
        for t in matched:
            ok, error = deliver(t, markdown, text, transport)
            if ok:
                logger.info(f"提醒已转发（{t.name}）：{reminder.get('title', '')}")
            else:
                logger.warning(f"提醒转发失败（{t.name}）：{error}")

    if background:
        threading.Thread(target=_run, name="notify-reminder", daemon=True).start()
    else:
        _run()
    return [t.name for t in matched]


def _on_reminder_triggered(**kwargs):
    try:
        forward_reminder(kwargs)
    except Exception as e:          # 通知是附加功能，任何问题都不能影响提醒本身
        logger.error(f"提醒转发处理失败：{e}")


def _on_startup(**kwargs):
    targets, problems = configured_targets()
    for p in problems:
        logger.warning(f"配置提示：{p}，已跳过")
    if targets:
        logger.info("通知目标：" + "、".join(f"{t.name}（{t.type}，提醒转发 {'/'.join(t.scopes)}）" for t in targets))


from src.core.infra import event_bus  # noqa: E402

event_bus.subscribe("reminder:triggered", _on_reminder_triggered)
event_bus.subscribe("app:startup", _on_startup)
