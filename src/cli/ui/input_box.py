"""Claude Code 风格的输入区：上下两条横线夹着输入行，下面一行提示。

    ────────────────────────────────────────────────────────
    > 输入内容
    ────────────────────────────────────────────────────────
      ? 快捷键 · / 命令                          会话：日常安排

- 不是全屏应用：只占输入需要的高度，提交后整块擦掉（由调用方留下一行 `> 消息`）。
- 输入 / 时在横线下方列出命令；选中带参数的命令后，接着列出它的参数选项（两级菜单）：
  ↑↓ 选择，Tab 只补全，Enter 补全并执行（带参数的命令先进入参数选择）。
- 空输入时按 ? 显示快捷键；空输入时连按两次 Ctrl-C 退出。
"""
import time
from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import History
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import SearchToolbar

from src.cli.application.commands import BY_NAME, COMMANDS, CommandSpec

MAX_INPUT_LINES = 12
MAX_SUGGESTIONS = 8
DOUBLE_CTRL_C_WINDOW = 2.0

PT_STYLES = {
    # auto：只用终端前景色 + dim 和基础色，不用 ansibrightblack（很多主题里它就是背景色，见 render.PALETTES）
    "auto": {"input": "", "border": "dim", "prompt": "bold", "hint": "dim", "accent": "ansiblue bold",
             "suggest": "", "suggest-meta": "dim", "suggest-selected": "ansiblue bold",
             "warn": "ansiyellow"},
    # dark / light：Claude Code 风格真彩色（与 render.PALETTES 一致）；input 是正在输入的文字
    "dark": {"input": "#FFFFFF", "border": "#888888", "prompt": "bold #FFFFFF", "hint": "#999999",
             "accent": "#D77757 bold", "suggest": "#FFFFFF", "suggest-meta": "#999999",
             "suggest-selected": "#B1B9F9 bold", "warn": "#FFC107"},
    "light": {"input": "#000000", "border": "#999999", "prompt": "bold #000000", "hint": "#666666",
              "accent": "#D77757 bold", "suggest": "#000000", "suggest-meta": "#666666",
              "suggest-selected": "#5769F7 bold", "warn": "#966C1E"},
}

SHORTCUTS = [
    ("Enter", "发送"), ("Alt+Enter", "换行（或先按 Esc 再按 Enter）"), ("/", "命令；带参数的命令会接着让你选参数"),
    ("↑ ↓", "历史记录 / 菜单选择"), ("Tab", "补全菜单里选中的项"), ("Ctrl-R", "搜索历史"),
    ("Ctrl-C", "清空输入 · 回复中停止等待 · 空输入连按两次退出"),
    ("Ctrl-L", "清屏"), ("Ctrl-D", "退出（服务继续运行）"), ("//文字", "发送以 / 开头的文字"),
]

# 运行时参数提供者：命令名 → [(值, 说明)]；由 REPL 注入（会话列表、日期等）
ArgProvider = Callable[[str], list[tuple[str, str]]]


class ExitRequested(Exception):
    """用户要求退出客户端（Ctrl-D 或空输入连按两次 Ctrl-C）。"""


@dataclass
class Item:
    label: str              # 菜单里显示的主文字
    meta: str               # 说明
    fill: str               # 选中后输入框里的内容
    submit: bool            # Enter 时是否直接执行（否则只补全，进入下一级）


class InputBox:
    def __init__(self, history: History, theme: str, color: bool, right_hint: Callable[[], str],
                 arg_provider: ArgProvider | None = None):
        self.buffer = Buffer(history=history, multiline=True, enable_history_search=False)
        self.theme = theme
        self.color = color
        self.right_hint = right_hint          # 回调：右下角显示的内容（会话名）
        self.arg_provider = arg_provider or (lambda name: [])
        self._selected = 0
        self._show_shortcuts = False
        self._last_ctrl_c = 0.0
        self._notice = ""
        self.search = SearchToolbar()

    # --- 两级菜单 ---

    def _stage(self) -> tuple[str, CommandSpec | None, str]:
        """当前输入处在哪一级：("none"|"command"|"arg", 命令, 已输入的部分)。"""
        text = self.buffer.text
        if not text.startswith("/") or text.startswith("//") or "\n" in text:
            return "none", None, ""
        if " " not in text:
            return "command", None, text
        name, _, rest = text.partition(" ")
        spec = BY_NAME.get(name)
        if spec is None or spec.arg == "none":
            return "none", None, ""
        return "arg", spec, rest

    def _arg_choices(self, spec: CommandSpec) -> list[tuple[str, str]]:
        if spec.arg == "choice":
            return list(spec.choices)
        if spec.arg == "dynamic":
            try:
                return self.arg_provider(spec.name)
            except Exception:
                return []
        return []

    def items(self) -> list[Item]:
        stage, spec, typed = self._stage()
        if stage == "command":
            out = []
            for c in COMMANDS:
                if not c.name.startswith(typed):
                    continue
                has_args = c.arg != "none"
                out.append(Item(c.name, c.help + ("  ›" if has_args else ""),
                                c.name + (" " if has_args else ""), submit=not has_args))
            # 已完整输入一个无参数命令：不再弹菜单，Enter 直接执行
            if len(out) == 1 and out[0].label == typed and out[0].submit:
                return []
            return out[:MAX_SUGGESTIONS]
        if stage == "arg":
            if spec.arg == "text":
                return []
            q = typed.strip().lower()
            out = []
            for value, desc in self._arg_choices(spec):
                if q and not (value.lower().startswith(q) or q in desc.lower()):
                    continue
                fill = f"{spec.name} {value}".rstrip()
                out.append(Item(value or "（不带参数）", desc, fill, submit=True))
            return out[:MAX_SUGGESTIONS]
        return []

    def _placeholder(self) -> str:
        stage, spec, typed = self._stage()
        if stage == "arg" and spec.arg == "text" and not typed:
            return f"{spec.placeholder}，然后按 Enter"
        return ""

    def _apply(self, submit_if_final: bool, event=None) -> bool:
        items = self.items()
        if not items:
            return False
        item = items[min(self._selected, len(items) - 1)]
        self.buffer.document = Document(item.fill, len(item.fill))
        self._selected = 0
        if submit_if_final and item.submit and event is not None:
            self._submit(event)
        return True

    def _submit(self, event) -> None:
        self.buffer.append_to_history()
        event.app.exit(result=self.buffer.text)

    # --- 布局 ---

    def _rule(self) -> Window:
        return Window(height=1, char="─", style="class:border")

    def _line_prefix(self, line_no: int, wrap_count: int):
        if line_no == 0 and wrap_count == 0:
            return [("class:prompt", "> ")]
        return [("", "  ")]

    def _panel_fragments(self):
        if self._show_shortcuts:
            out = []
            for k, v in SHORTCUTS:
                out += [("class:accent", f"  {k:<12}"), ("class:suggest-meta", f"{v}\n")]
            return out
        placeholder = self._placeholder()
        if placeholder:
            return [("class:suggest-meta", f"  {placeholder}\n")]
        out = []
        items = self.items()
        sel = min(self._selected, len(items) - 1) if items else 0
        width = max([_width(i.label) for i in items] + [10]) + 2
        for i, it in enumerate(items):
            style = "class:suggest-selected" if i == sel else "class:suggest"
            pad = " " * (width - _width(it.label))
            out += [(style, f"  {'❯' if i == sel else ' '} {it.label}{pad}"), ("class:suggest-meta", f"{it.meta}\n")]
        return out

    def _left_hint(self):
        if self._notice:
            return [("class:warn", f"  {self._notice}")]
        if self._show_shortcuts:
            return [("class:hint", "  再按 ? 或开始输入即可关闭")]
        stage, _, _ = self._stage()
        if stage != "none" and self.items():
            return [("class:hint", "  ↑↓ 选择 · Enter 确认 · Tab 补全")]
        return [("class:hint", "  ? 快捷键 · / 命令 · Alt+Enter 换行")]

    def _right_hint(self):
        return [("class:hint", f"{self.right_hint()}  ")]

    def _layout(self) -> Layout:
        input_window = Window(
            BufferControl(self.buffer, search_buffer_control=self.search.control),
            height=Dimension(min=1, max=MAX_INPUT_LINES),
            dont_extend_height=True,
            wrap_lines=True,
            get_line_prefix=self._line_prefix,
            style="class:input",
        )
        has_panel = Condition(lambda: self._show_shortcuts or bool(self._placeholder()) or bool(self.items()))
        root = HSplit([
            self._rule(),
            input_window,
            self._rule(),
            ConditionalContainer(
                Window(FormattedTextControl(self._panel_fragments), dont_extend_height=True,
                       height=Dimension(max=max(len(SHORTCUTS), MAX_SUGGESTIONS))),
                filter=has_panel),
            VSplit([
                Window(FormattedTextControl(self._left_hint), height=1),
                Window(FormattedTextControl(self._right_hint), height=1, align=WindowAlign.RIGHT),
            ]),
            self.search,
        ])
        return Layout(root, focused_element=input_window)

    # --- 按键 ---

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()
        menu = Condition(lambda: bool(self.items()))
        empty = Condition(lambda: self.buffer.text == "")

        def enter(event):
            if self._apply(submit_if_final=True, event=event):
                return
            self._submit(event)

        # Ctrl-J 也按提交：终端在普通模式下会把提前敲下的回车转成 \n（Ctrl-J）
        kb.add("enter")(enter)
        kb.add("c-j")(enter)

        @kb.add("escape", "enter")
        def _(event):
            self.buffer.insert_text("\n")

        @kb.add("tab", filter=menu)
        def _(event):
            self._apply(submit_if_final=False)

        @kb.add("up", filter=menu, eager=True)
        def _(event):
            n = len(self.items())
            self._selected = (self._selected - 1) % n

        @kb.add("down", filter=menu, eager=True)
        def _(event):
            n = len(self.items())
            self._selected = (self._selected + 1) % n

        @kb.add("?", filter=empty)
        def _(event):
            self._show_shortcuts = not self._show_shortcuts

        @kb.add("c-c")
        def _(event):
            if self.buffer.text:
                self.buffer.reset()
                self._notice = ""
                return
            now = time.monotonic()
            if now - self._last_ctrl_c < DOUBLE_CTRL_C_WINDOW:
                event.app.exit(exception=ExitRequested())
                return
            self._last_ctrl_c = now
            self._notice = "再按一次 Ctrl-C 退出"

        @kb.add("c-d", filter=empty)
        def _(event):
            event.app.exit(exception=ExitRequested())

        @kb.add("c-l")
        def _(event):
            event.app.renderer.clear()

        return kb

    def _on_change(self, _buffer) -> None:
        self._selected = 0
        self._show_shortcuts = False
        self._notice = ""

    async def read(self, default: str = "") -> str:
        """读一条输入。退出请求抛 ExitRequested。"""
        self.buffer.reset(Document(default, len(default)))
        self._selected = 0
        self._show_shortcuts = False
        self._notice = ""
        self.buffer.on_text_changed += self._on_change
        app = Application(
            layout=self._layout(),
            key_bindings=merge_key_bindings([load_key_bindings(), self._bindings()]),
            style=Style.from_dict(PT_STYLES[self.theme]),
            color_depth=None if self.color else ColorDepth.MONOCHROME,
            erase_when_done=True,
            full_screen=False,
            mouse_support=False,
        )
        try:
            return await app.run_async()
        finally:
            self.buffer.on_text_changed -= self._on_change


def _width(s: str) -> int:
    from wcwidth import wcswidth
    w = wcswidth(s)
    return w if w >= 0 else len(s)
