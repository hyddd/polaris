"""斜杠命令白名单。

未知的 /xxx 在本地报错，不交给模型。要发送以 / 开头的普通文字，用 // 开头（发送时去掉一个 /）；
但如果去掉后正好是服务端命令（比如 //reset），拒绝发送——服务端会把它当命令执行，等于绕过白名单。
"""
from dataclasses import dataclass

# 服务端 src/session/commands.py 识别的命令；聊天里以这些开头的文字会被服务端直接执行
SERVER_COMMANDS = {"/reset", "/compact", "/status", "/cache", "/help", "/new", "/sessions",
                   "/session", "/rename", "/reload", "/cleanup"}


@dataclass(frozen=True)
class CommandSpec:
    name: str
    usage: str
    help: str
    where: str   # local / session_api / query / server
    # 参数：none 无参数；choice 固定选项（choices）；dynamic 运行时提供（会话、日期）；text 自由输入
    arg: str = "none"
    choices: tuple[tuple[str, str], ...] = ()   # (值, 说明)；值为空串表示不带参数
    placeholder: str = ""


COMMANDS = [
    CommandSpec("/help", "/help", "显示帮助", "local"),
    CommandSpec("/todos", "/todos [pending|in_progress|done|all]", "查看待办（不经过模型）", "query",
                arg="choice", choices=(("all", "全部"), ("pending", "待办"), ("in_progress", "进行中"), ("done", "已完成"))),
    CommandSpec("/calendar", "/calendar [YYYY-MM-DD]", "查看日程（不经过模型）", "query", arg="dynamic"),
    CommandSpec("/reminders", "/reminders [active|paused|failed|cancelled|all]", "查看提醒（不经过模型）", "query",
                arg="choice", choices=(("all", "全部"), ("active", "活跃"), ("paused", "已暂停"),
                                       ("failed", "未送达"), ("cancelled", "已完成"))),
    # 会话命令与 Claude Code 一致：/resume 切换（不带参数打开选择器），/clear 开新会话（旧会话保留）
    CommandSpec("/resume", "/resume [名称或ID]", "恢复其他会话（不带参数打开会话选择器）", "session_api", arg="dynamic"),
    CommandSpec("/clear", "/clear", "开始新会话并清屏（当前会话会保留，可用 /resume 回来）", "session_api"),
    CommandSpec("/rename", "/rename <新名称>", "重命名当前会话", "session_api", arg="text", placeholder="输入新名称"),
    CommandSpec("/history", "/history [条数]", "显示当前会话最近的消息", "session_api",
                arg="choice", choices=(("10", "最近 10 条"), ("20", "最近 20 条"), ("50", "最近 50 条"))),
    CommandSpec("/view", "/view", "按 Markdown 重新排版显示上一条回复", "local"),
    CommandSpec("/tools", "/tools", "展开上一轮的工具参数和返回结果", "local"),
    CommandSpec("/status", "/status", "连接状态与当前会话（不测试模型）", "query"),
    CommandSpec("/theme", "/theme auto|light|dark", "切换配色", "local",
                arg="choice", choices=(("auto", "跟随终端配色"), ("dark", "深色背景"), ("light", "浅色背景"))),
    CommandSpec("/compact", "/compact", "压缩当前会话上下文（会调用模型，执行前确认）", "server"),
    CommandSpec("/cache", "/cache", "查看模型提示词缓存命中统计", "server"),
    CommandSpec("/quit", "/quit", "退出客户端（不停止服务）", "local"),
]
BY_NAME = {c.name: c for c in COMMANDS}

BLOCKED = {
    "/reset": "会清空当前会话的全部记忆，后端还没有统一的确认机制",
    "/cleanup": "会清理所有过期的日程/待办/提醒，影响范围是全局",
    "/reload": "会热重载服务端配置并重启渠道",
}


@dataclass(frozen=True)
class Parsed:
    kind: str          # chat / command / error / empty
    text: str = ""     # chat 的正文，或 error 的说明
    name: str = ""     # command 名
    arg: str = ""


def parse_input(line: str) -> Parsed:
    stripped = line.strip()
    if not stripped:
        return Parsed("empty")
    if stripped.startswith("//"):
        text = stripped[1:]
        first = text.split(maxsplit=1)[0]
        if first in SERVER_COMMANDS:
            return Parsed("error", f"不能发送「{text}」：服务端会把它当作 {first} 命令执行。")
        return Parsed("chat", text)
    if not stripped.startswith("/"):
        return Parsed("chat", line.strip("\n"))
    parts = stripped.split(maxsplit=1)
    name, arg = parts[0], (parts[1].strip() if len(parts) > 1 else "")
    if name in BLOCKED:
        return Parsed("error", f"{name} 在终端客户端里暂不开放：{BLOCKED[name]}。需要时请在网页上操作。")
    if name not in BY_NAME:
        return Parsed("error", f"未知命令 {name}，输入 /help 查看可用命令。要发送以 / 开头的文字，请用 // 开头。")
    return Parsed("command", name=name, arg=arg)


def help_text() -> list[tuple[str, str]]:
    return [(c.usage, c.help) for c in COMMANDS]
