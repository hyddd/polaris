"""通知目标：企业微信群机器人（notify.webhooks）和 QQ / 飞书接收人（notify.recipients）。

两类目标地位相同：
- 提醒到点时，按每个目标的 scopes 转发（public / private，不写则都转发）；
- 主动通知（接口、网页、AI 工具）按目标名称发送，不受 scopes 限制。
只能发给配置里有名字的目标；webhook 地址、QQ / 飞书账号只留在服务端配置里，对外只暴露名称。
"""
from dataclasses import dataclass, field

SCOPES = ("public", "private")
# recipients 的 channel 前缀 → (目标类型, 使用的渠道插件)
CHANNEL_PREFIXES = {"qq:": ("qq", "qq"), "feishu:": ("feishu", "feishu"), "feishu-chat:": ("feishu-chat", "feishu")}


@dataclass
class Target:
    name: str
    type: str                       # wecom / qq / feishu（私聊）/ feishu-chat（群聊）
    scopes: list = field(default_factory=lambda: list(SCOPES))
    url: str = ""                   # wecom
    channel: str = ""               # qq / feishu / feishu-chat，如 "qq:<openid>"

    @property
    def plugin(self) -> str:
        """发送用的渠道插件名；wecom 不经过渠道插件。"""
        return {"qq": "qq", "feishu": "feishu", "feishu-chat": "feishu"}.get(self.type, "")

    @property
    def address(self) -> str:
        """渠道里的接收方：openid / open_id / chat_id。"""
        return self.channel.split(":", 1)[1] if ":" in self.channel else ""

    def public_dict(self) -> dict:
        """对外展示用：不含 url 和账号。"""
        return {"name": self.name, "type": self.type, "scopes": list(self.scopes)}


def _scopes(item: dict, label: str, problems: list) -> list | None:
    scopes = item.get("scopes") or list(SCOPES)
    if not isinstance(scopes, list) or any(s not in SCOPES for s in scopes):
        problems.append(f"{label} 的 scopes 只能包含 public、private")
        return None
    return scopes


def load_targets(webhooks, recipients) -> tuple[list[Target], list[str]]:
    """校验 notify.webhooks 和 notify.recipients，返回 (可用目标, 问题说明)。有问题的条目跳过，不影响其他条目。"""
    targets, problems = [], []
    for key, raw in (("notify.webhooks", webhooks), ("notify.recipients", recipients)):
        if raw in (None, []):
            continue
        if not isinstance(raw, list):
            problems.append(f"{key} 必须是列表")
            continue
        for i, item in enumerate(raw):
            label = f"{key} 第 {i + 1} 项"
            if not isinstance(item, dict):
                problems.append(f"{label} 格式不对，应为对象")
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                problems.append(f"{label} 缺少 name")
                continue
            label = f"{label}（{name}）"
            scopes = _scopes(item, label, problems)
            if scopes is None:
                continue
            if key == "notify.webhooks":
                kind = str(item.get("type") or "").strip().lower()
                url = str(item.get("url") or "").strip()
                if kind != "wecom":
                    problems.append(f"{label} 的 type 只支持 wecom：{kind or '（未填写）'}")
                    continue
                if not url.startswith("https://"):
                    problems.append(f"{label} 的 url 必须是 https:// 开头的完整地址")
                    continue
                targets.append(Target(name=name, type="wecom", scopes=scopes, url=url))
            else:
                channel = str(item.get("channel") or "").strip()
                prefix = next((p for p in sorted(CHANNEL_PREFIXES, key=len, reverse=True) if channel.startswith(p)), None)
                if not prefix or not channel[len(prefix):]:
                    problems.append(f"{label} 的 channel 必须是 qq:<openid>、feishu:<open_id> 或 feishu-chat:<chat_id>")
                    continue
                targets.append(Target(name=name, type=CHANNEL_PREFIXES[prefix][0], scopes=scopes, channel=channel))
    seen, unique = set(), []
    for t in targets:
        if t.name in seen:
            problems.append(f"通知目标重名：{t.name}（只保留第一个）")
            continue
        seen.add(t.name)
        unique.append(t)
    return unique, problems


def configured_targets() -> tuple[list[Target], list[str]]:
    from src.core.config import config
    return load_targets(config.get("notify.webhooks", []), config.get("notify.recipients", []))
