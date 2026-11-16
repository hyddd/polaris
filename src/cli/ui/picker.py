"""会话选择器，交互与 Claude Code 的 /resume 选择器一致（内联列表，不是全屏）：

    ↑↓ 或 j/k 移动 · Enter 恢复 · 1–9 直接恢复第几个 · 空格预览 · Ctrl-R 重命名
    / 或直接输入文字进入搜索 · Esc 退出搜索 / 关闭选择器

列表按最近活跃排序，默认选中第一个。每行显示会话名、距上次活跃多久、消息数。
预览、重命名需要请求服务端，所以选择器先退出、由调用方处理完再带着原来的位置和搜索词重新打开。
"""
from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style

from src.cli.ui.input_box import PT_STYLES
from src.cli.ui.sanitize import sanitize
from src.cli.ui.views import relative_time

MAX_ROWS = 12


@dataclass
class PickerResult:
    action: str               # resume / preview / rename
    session: dict
    index: int = 0
    query: str = ""


def _display_width(s: str) -> int:
    from wcwidth import wcswidth
    w = wcswidth(s)
    return w if w >= 0 else len(s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _display_width(s))


def _matches(s: dict, query: str) -> bool:
    q = query.lower()
    return q in s["name"].lower() or q in s["session_id"].lower()


async def pick_session(sessions: list[dict], theme: str, color: bool, current: str | None = None,
                       index: int = 0, query: str = "", title: str = "恢复会话") -> PickerResult | None:
    """返回 PickerResult；Esc / Ctrl-C 返回 None。"""
    state = {"i": index, "q": query, "searching": bool(query)}

    def visible() -> list[dict]:
        return [s for s in sessions if _matches(s, state["q"])] if state["q"] else list(sessions)

    def clamp():
        n = len(visible())
        state["i"] = min(max(state["i"], 0), max(n - 1, 0))

    def fragments():
        items = visible()
        clamp()
        out = [("class:accent", f"  {title}"), ("class:hint", f"  共 {len(sessions)} 个\n")]
        if state["searching"]:
            out.append(("class:prompt", f"  搜索：{state['q']}▏\n"))
        if not items:
            out.append(("class:suggest-meta", "  （没有匹配的会话）\n" if sessions else "  （还没有会话）\n"))
        start = max(0, min(state["i"] - MAX_ROWS // 2, len(items) - MAX_ROWS))
        name_w = max([_display_width(sanitize(s["name"])) for s in items] + [8]) + 2
        for pos in range(start, min(start + MAX_ROWS, len(items))):
            s = items[pos]
            sel = pos == state["i"]
            style = "class:suggest-selected" if sel else "class:suggest"
            num = f"{pos + 1}." if pos < 9 else "  "
            meta = f"{relative_time(s.get('last_active'))} · {s.get('message_count', 0)} 条消息"
            if s["session_id"] == current:
                meta += " · 当前"
            out += [(style, f"  {'❯' if sel else ' '} {num:<3}{_pad(sanitize(s['name']), name_w)}"),
                    ("class:suggest-meta", meta + "\n")]
        if len(items) > MAX_ROWS:
            out.append(("class:suggest-meta", f"  …共 {len(items)} 个，↑↓ 滚动\n"))
        hint = ("输入文字过滤 · Backspace 删除 · Esc 退出搜索 · Enter 恢复" if state["searching"] else
                "↑↓ 选择 · Enter 恢复 · 1–9 快选 · 空格预览 · Ctrl-R 重命名 · / 搜索 · Esc 关闭")
        out.append(("class:hint", f"  {hint}"))
        return out

    kb = KeyBindings()

    def done(event, action):
        items = visible()
        if items:
            event.app.exit(result=PickerResult(action, items[state["i"]], state["i"], state["q"]))

    @kb.add("up")
    def _(event):
        state["i"] -= 1
        clamp()

    @kb.add("down")
    def _(event):
        state["i"] += 1
        clamp()

    @kb.add("enter")
    @kb.add("c-j")
    def _(event):
        done(event, "resume")

    @kb.add("c-r")
    def _(event):
        done(event, "rename")

    @kb.add("escape", eager=True)
    def _(event):
        if state["searching"]:
            state["searching"], state["q"], state["i"] = False, "", 0
        else:
            event.app.exit(result=None)

    @kb.add("c-c")
    @kb.add("c-d")
    def _(event):
        event.app.exit(result=None)

    @kb.add("backspace")
    @kb.add("c-h")
    def _(event):
        if state["searching"]:
            state["q"] = state["q"][:-1]
            state["i"] = 0

    @kb.add(Keys.Any)
    def _(event):
        ch = event.data
        if not ch or not ch.isprintable():
            return
        if state["searching"]:
            state["q"] += ch
            state["i"] = 0
        elif ch in ("j", "k"):
            state["i"] += 1 if ch == "j" else -1
            clamp()
        elif ch == " ":
            done(event, "preview")
        elif ch.isdigit() and ch != "0":
            items = visible()
            if int(ch) <= len(items):
                state["i"] = int(ch) - 1
                done(event, "resume")
        else:
            # 和 Claude Code 一样：/ 或其他可打印字符进入搜索
            state["searching"] = True
            state["q"] = "" if ch == "/" else ch
            state["i"] = 0

    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(fragments, focusable=True), dont_extend_height=True)])),
        key_bindings=kb,
        style=Style.from_dict(PT_STYLES[theme]),
        color_depth=None if color else ColorDepth.MONOCHROME,
        erase_when_done=True,
        full_screen=False,
    )
    return await app.run_async()
