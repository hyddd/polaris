"""唯一的终端输出适配层。所有写屏都经过这里，统一做控制字符过滤和配色降级。

视觉风格参照 Claude Code：
- 回复以 ⏺ 开头，续行缩进两格；
- 工具调用一行 `⏺ 工具名(参数)`，下一行 `  ⎿  结果摘要 · 耗时`；
- 等待时最后一行是动画 `✻ 思考中… (3s · Ctrl-C 中断)`，有新内容要写时先擦掉它。

流式文字直接追加写，不全量重绘。Rich 只用来排版（面板、表格、Markdown），
不启用 Live 自动刷新，不和 prompt_toolkit 抢光标。
"""
import json
import os
import sys
import time
from typing import TextIO

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.cli.ui.sanitize import sanitize

BULLET = "⏺"
RESULT = "⎿"
INDENT = "  "
SPINNER_FRAMES = "·✢✳✶✻✽✻✶✳✢"
SPINNER_DELAY = 0.5   # 这么久没有新输出才显示动画，避免流式输出时一闪一闪

PALETTES = {
    # auto 跟随终端配色：次要文字用"前景色 + 暗淡（SGR 2）"，不用 bright_black / black / white 这些调色板编号。
    # 很多主题（如 iTerm2 Solarized Dark，COLORFGBG=12;8）的背景色就是 8 号亮黑，用它写字会和背景重合。
    "auto": {"text": "", "dim": "dim", "accent": "bold blue", "brand": "blue", "ok": "green", "warn": "yellow",
             "err": "red", "you": "dim", "bullet": "default", "tool": "bold", "border": "dim"},
    # dark / light：参照 Claude Code 默认主题的 24 位真彩色，不受终端调色板影响。
    # you 带背景色：用户输入回显成一整行底条。
    "dark": {"text": "#FFFFFF", "dim": "#999999", "accent": "bold #D77757", "brand": "#D77757",
             "ok": "#4EBA65", "warn": "#FFC107", "err": "#FF6B80", "you": "#B1B9F9 on #373737",
             "bullet": "#FFFFFF", "tool": "bold #FFFFFF", "border": "#888888"},
    "light": {"text": "#000000", "dim": "#666666", "accent": "bold #D77757", "brand": "#D77757",
              "ok": "#2C7A39", "warn": "#966C1E", "err": "#AB2B3F", "you": "#3D4FD6 on #E8E8E8",
              "bullet": "#000000", "tool": "bold #000000", "border": "#999999"},
}


def color_enabled(mode: str, stream: TextIO) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def is_terminal(stream: TextIO) -> bool:
    """能不能用光标控制（动画、原地改写）。和颜色无关：NO_COLOR 只关颜色。"""
    return os.environ.get("TERM") != "dumb" and hasattr(stream, "isatty") and stream.isatty()


def summarize_args(args, limit: int = 60) -> str:
    if not isinstance(args, dict) or not args:
        return ""
    parts = []
    for k, v in args.items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        parts.append(f"{k}={s}")
    out = sanitize(" ".join(parts)).replace("\n", " ")
    return out if len(out) <= limit else out[: limit - 1] + "…"


def summarize_result(result: str | None, limit: int = 72) -> str:
    """工具结果的一行摘要：第一行非空内容，超长截断，多行时注明总行数。"""
    if result is None:
        return "（没有收到结果）"
    lines = [ln.strip() for ln in sanitize(result).splitlines() if ln.strip()]
    if not lines:
        return "（空）"
    first = lines[0] if len(lines[0]) <= limit else lines[0][: limit - 1] + "…"
    return f"{first}  …共 {len(lines)} 行" if len(lines) > 1 else first


class Renderer:
    def __init__(self, stream: TextIO | None = None, color: str = "auto", theme: str = "auto"):
        self.stream = stream or sys.stdout
        self.color = color_enabled(color, self.stream)
        self.tty = is_terminal(self.stream)
        self.console = Console(file=self.stream, force_terminal=self.color, no_color=not self.color,
                               highlight=False, soft_wrap=True, emoji=False, markup=False)
        self.set_theme(theme)
        self._at_line_start = True
        self._buf = ""
        self._last_flush = 0.0
        self._in_block = False        # 正在写一段 ⏺ 回复：续行要缩进
        self._need_indent = False
        self._spin_label: str | None = None
        self._spin_since = 0.0
        self._spin_visible = False
        self._last_output = 0.0

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.style = PALETTES[theme]

    def _s(self, name: str | None) -> str:
        return self.style.get(name, name) if name else ""

    @property
    def width(self) -> int:
        return self.console.width

    # --- 基础输出 ---

    def _raw(self, s: str) -> None:
        self.stream.write(s)
        self.stream.flush()

    def _write(self, text: str, style: str | None = None) -> None:
        if not text:
            return
        self._hide_spinner()
        # 没指定样式的正文用主题的 text 色（auto 为空 = 终端前景色）
        self.console.print(Text(text, style=self._s(style or "text")), end="")
        self._at_line_start = text.endswith("\n")
        self._last_output = time.monotonic()

    def ensure_newline(self) -> None:
        self.flush()
        self._hide_spinner()
        if not self._at_line_start:
            self._write("\n")

    def line(self, text: str = "", style: str | None = None) -> None:
        self.end_block()
        self.ensure_newline()
        self._write(sanitize(text) + "\n", style)

    def dim(self, text: str) -> None:
        self.line(text, "dim")

    def warn(self, text: str) -> None:
        self.line(text, "warn")

    def error(self, text: str) -> None:
        self.line(text, "err")

    def ok(self, text: str) -> None:
        self.line(text, "ok")

    def blank(self) -> None:
        self.ensure_newline()
        self._write("\n")

    # --- ⏺ 回复块 ---

    def user_echo(self, text: str) -> None:
        """提交后的用户消息：`> 消息`，多行时续行缩进。

        主题给 you 配了背景色时（dark/light），每行补空格铺满终端宽度，显示成整行底条。
        """
        self.ensure_newline()
        lines = sanitize(text).split("\n")
        rows = ["> " + lines[0]] + ["  " + ln for ln in lines[1:]]
        if self.color and " on " in self._s("you"):
            from rich.cells import cell_len
            rows = [f" {r}".ljust(self.width - 1 - (cell_len(r) - len(r))) for r in rows]
            for r in rows:
                self._write(r, "you")
                self._write("\n")
            return
        self._write("\n".join(rows) + "\n", "you")

    def begin_block(self) -> None:
        if self._in_block:
            return
        self.ensure_newline()
        self._write(f"{BULLET} ", "bullet")
        self._in_block = True
        self._need_indent = False

    def end_block(self) -> None:
        if self._in_block:
            self.flush()
            self._in_block = False
            self.ensure_newline()

    def message(self, content: str) -> None:
        """一整块独立内容（命令输出、确认结果）作为一段 ⏺ 回复。"""
        self.end_block()
        self.begin_block()
        self._block_text(sanitize(content))
        self.end_block()

    def text(self, delta: str) -> None:
        """流式回复片段，按 ~40ms 合并刷新。"""
        self.begin_block()
        self._buf += sanitize(delta)
        if time.monotonic() - self._last_flush >= 0.04:
            self.flush()

    def flush(self) -> None:
        if self._buf:
            buf, self._buf = self._buf, ""
            if self._in_block:
                self._block_text(buf)
            else:
                self._write(buf)
        self._last_flush = time.monotonic()

    def _block_text(self, text: str) -> None:
        pieces = text.split("\n")
        for i, piece in enumerate(pieces):
            if piece:
                if self._need_indent:
                    self._write(INDENT)
                    self._need_indent = False
                self._write(piece)
            if i < len(pieces) - 1:
                self._write("\n")
                self._need_indent = True

    # --- 工具调用 ---

    def tool_started(self, call_id: str, tool: str, args) -> None:
        self.end_block()
        self.ensure_newline()
        self._write(f"{BULLET} ", "bullet")
        self._write(sanitize(tool), "tool")
        detail = summarize_args(args)
        self._write(f"({detail})\n" if detail else "\n", "dim")

    def tool_finished(self, call_id: str, tool: str, result: str | None, duration: float | None) -> None:
        self.end_block()
        self.ensure_newline()
        took = f" · {duration:.1f}s" if duration is not None else ""
        self._write(f"{INDENT}{RESULT}  ", "dim")
        self._write(summarize_result(result), "dim")
        self._write(f"{took}\n", "dim")

    # --- 等待动画 ---

    def spinner(self, label: str | None) -> None:
        """设置等待动画的文字；None 关闭。只在终端里显示，由 tick() 驱动。"""
        if label is None:
            self._hide_spinner()
        elif self._spin_label is None:
            self._spin_since = time.monotonic()
        self._spin_label = label

    def tick(self) -> None:
        """定时调用：刷新流式文字，必要时画等待动画。"""
        self.flush()
        if not (self.tty and self._spin_label):
            return
        now = time.monotonic()
        if now - self._last_output < SPINNER_DELAY:
            return
        if not self._at_line_start and not self._spin_visible:
            return   # 光标在一行中间（回复写到一半），不能另起动画
        frame = SPINNER_FRAMES[int(now * 8) % len(SPINNER_FRAMES)]
        elapsed = int(now - self._spin_since)
        text = Text()
        text.append(f"{frame} ", self._s("brand"))
        text.append(f"{self._spin_label}… ", self._s("brand"))
        text.append(f"({elapsed}s · Ctrl-C 中断)", self._s("dim"))
        self._raw("\r\x1b[2K")
        self.console.print(text, end="")
        self._spin_visible = True

    def _hide_spinner(self) -> None:
        if self._spin_visible:
            self._raw("\r\x1b[2K")
            self._spin_visible = False
            self._at_line_start = True

    # --- 排版块 ---

    def welcome(self, title: str, rows: list[tuple[str, str]], subtitle: str = "") -> None:
        """启动时的圆角欢迎面板。"""
        self.ensure_newline()
        head = Text()
        head.append("✦ ", self._s("brand"))
        head.append(title, self._s("accent"))
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=self._s("dim"), no_wrap=True)
        grid.add_column()
        for k, v in rows:
            grid.add_row(k, Text(sanitize(v)))
        parts = [head, Text("")]
        if subtitle:
            parts += [Text(subtitle, style=self._s("dim")), Text("")]
        parts.append(grid)
        self.console.print(Panel(Group(*parts), box=box.ROUNDED, border_style=self._s("brand"),
                                 padding=(0, 2), expand=False, width=min(self.width, 72)))
        self._at_line_start = True

    def markdown(self, text: str) -> None:
        self.end_block()
        self.ensure_newline()
        self.console.print(Markdown(sanitize(text)))
        self._at_line_start = True

    def table(self, columns: list[str], rows: list[list[str]], title: str | None = None) -> None:
        self.end_block()
        self.ensure_newline()
        t = Table(title=title, box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False,
                  header_style=self._s("dim"), title_style=self._s("accent"), title_justify="left")
        for c in columns:
            t.add_column(c, overflow="fold")
        for r in rows:
            t.add_row(*[Text(sanitize(str(x))) for x in r])
        self.console.print(t)
        self._at_line_start = True

    def pairs(self, rows: list[tuple[str, str]], key_style: str = "accent", value_style: str | None = "dim") -> None:
        """两列对齐的说明（命令帮助、快捷键、状态）。"""
        self.end_block()
        self.ensure_newline()
        grid = Table.grid(padding=(0, 3))
        grid.add_column(style=self._s(key_style), no_wrap=True)
        grid.add_column(style=self._s(value_style))
        for k, v in rows:
            grid.add_row(Text("  " + sanitize(k)), Text(sanitize(v)))
        self.console.print(grid)
        self._at_line_start = True

    def clear_screen(self) -> None:
        self._hide_spinner()
        self.console.clear()
        self._at_line_start = True
