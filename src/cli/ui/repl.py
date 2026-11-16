"""交互模式：滚动式对话，视觉风格参照 Claude Code。

- 输入：紧贴对话的圆角输入框（ui/input_box.py），提交后擦掉，留下一行 `> 消息`。
- 输出：Renderer 统一写屏；回复以 ⏺ 开头，工具调用带 ⎿ 结果摘要，等待时有动画。
- 回复进行中终端切到 raw 模式接管按键：Ctrl-C 取消本轮（断开连接，服务端会停在下一步并保存已发生的部分），
  其他键入的字符留作草稿，回复结束后放回输入框；Enter 不会偷偷发出第二条。
- 斜杠命令走白名单，会话切换走会话接口，不依赖聊天命令返回的会话 ID。
"""
import asyncio
import json
import os
import signal
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import ColorDepth

from src.cli.application.commands import parse_input, help_text
from src.cli.application.controller import (Controller, ServerInfo, SessionNotFound, describe_instance,
                                            instance_badge)
from src.cli.application.state import RunState
from src.cli.client import ClientError
from src.cli.config import ClientConfig, THEMES
from src.cli.protocol.events import (
    TEXT_DELTA, MESSAGE, TOOL_STARTED, TOOL_FINISHED, WARNING, FAILED,
    STATUS_UNKNOWN, STATUS_INTERRUPTED,
)
from src.cli.storage import StateStore, write_private
from src.cli.ui import views
from src.cli.ui.input_box import InputBox, ExitRequested, SHORTCUTS
from src.cli.ui.picker import pick_session
from src.cli.ui.render import Renderer

SUBTITLE = "你的私人效率助手 · 日程 · 待办 · 笔记 · 提醒"
START_HINT = "  /help 查看命令 · Ctrl-C 只停止等待，已执行的操作不会撤销；删除前模型会先问你确认"


def _home_relative(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


class Repl:
    def __init__(self, ctrl: Controller, cfg: ClientConfig, store: StateStore, renderer: Renderer):
        self.ctrl = ctrl
        self.cfg = cfg
        self.store = store
        self.r = renderer
        self.server: ServerInfo | None = None
        self.instance: dict | None = None   # 服务模式和名字（/api/instance）
        self.session_id: str | None = None
        self.session_name: str = ""
        self.last: RunState | None = None
        self.draft = ""
        self._sessions: list[dict] = []   # 会话列表缓存，给 /resume 的参数菜单用
        # 新会话在发第一条消息时才创建（和 Claude Code 一样，打开又退出不留空会话）
        self._pending_name: str | None = None   # -n / 建会话前的 /rename 指定的名字
        self._auto_title = False                 # 本会话还没起过名：首条消息后用它自动起名

    # ------------------------------------------------------------------ 启动

    async def run(self, mode: str = "new", target: str | None = None, name: str | None = None) -> int:
        """启动方式与 Claude Code 一致：
        new（默认）新会话；continue（-c）继续最近的会话；resume（--resume [名称或ID]）选择器或直接恢复。
        """
        code = await self._check_server()
        if code is not None:
            return code
        self.input = self._make_input()
        try:
            if mode == "continue":
                chosen = await self._most_recent()
                if chosen is None:
                    self.r.error("没有可以继续的会话。直接运行 ./cli.sh 开始新会话。")
                    return 4
            elif mode == "resume":
                chosen = await self._resume_target(target, exit_on_cancel=True)
                if chosen is None:
                    self.r.dim("  已退出客户端；Polaris 服务仍在后台运行。")
                    return 0 if not target else 4
            else:
                chosen = None
                self._start_new(name)
                await self._refresh_sessions()      # 给 /resume 的参数菜单用
        except ClientError as e:
            self.r.error(str(e))
            return e.exit_code
        except (KeyboardInterrupt, EOFError):
            return 0
        if chosen is not None and not await self._switch_to(chosen, show_history=True):
            return 4
        self.r.dim(START_HINT)
        self.r.blank()
        return await self._loop()

    async def _check_server(self) -> int | None:
        self.server = info = await self.ctrl.probe()
        if not info.reachable:
            self.r.error(f"✗ 连不上 Polaris 服务：{self.cfg.url}")
            self.r.dim(f"  {info.error}")
            self.r.dim("  服务没在运行的话，在项目目录执行 ./start-personal.sh（团队服务用 ./start-team.sh）启动。"
                       "客户端不会替你启动服务。")
            return info.error.exit_code
        if info.missing:
            self.r.error("✗ 服务端缺少终端客户端依赖的接口：" + "、".join(info.missing))
            return 4
        status = "● 在线" if info.fixed_backend else "● 在线（修复前的旧版本）"
        try:
            self.instance = await self.ctrl.instance()
        except ClientError:
            self.instance = None
        self.r.welcome("欢迎使用 Polaris", [
            ("服务", f"{self.cfg.url}  {status}"),
            ("模式", describe_instance(self.instance)),
            ("目录", _home_relative(os.getcwd())),
        ], subtitle=SUBTITLE)
        if not info.fixed_backend:
            self.r.warn("⚠ 服务端还在运行 2026-11-09 修复之前的代码：流式对话每一轮都会把会话历史覆盖成只剩最后一条回复。")
            self.r.warn("  请先重启服务：./stop-personal.sh && ./start-personal.sh（团队服务用 -team 的脚本）")
            if not await self._confirm("仍要继续吗？[y/N] "):
                return 0
        return None

    def _make_input(self) -> InputBox:
        if self.cfg.persist_history:
            if not self.cfg.history_file.exists():
                write_private(self.cfg.history_file, "")
            history = FileHistory(str(self.cfg.history_file))
        else:
            history = InMemoryHistory()
        return InputBox(history, theme=self.r.theme, color=self.r.color,
                        right_hint=self._right_hint,
                        arg_provider=self._arg_choices)

    def _right_hint(self) -> str:
        badge = instance_badge(self.instance)
        return f"{badge}  会话：{self.session_name or '新会话'}" if badge else f"会话：{self.session_name or '新会话'}"

    def _arg_choices(self, name: str) -> list[tuple[str, str]]:
        """命令参数菜单里运行时才知道的选项。只读本地缓存，不在按键时发请求。"""
        if name == "/resume":
            out = [("", "打开会话选择器")]
            for s in self._sessions:
                if s["session_id"] == self.session_id:
                    continue
                meta = f"{s['name']} · {s.get('message_count', 0)} 条消息 · {views.relative_time(s.get('last_active'))}"
                out.append((s["session_id"], meta))
            return out
        if name == "/calendar":
            today = date.today()
            out = [("", "全部日程")]
            for offset, label in ((0, "今天"), (1, "明天"), (2, "后天")):
                d = today + timedelta(days=offset)
                out.append((d.isoformat(), f"{label}（周{'一二三四五六日'[d.weekday()]}）"))
            return out
        return []

    async def _refresh_sessions(self) -> list[dict]:
        sessions, _ = await self.ctrl.list_sessions()
        self._sessions = sessions
        return sessions

    async def _ask(self, message: str, default: str = "") -> str:
        p = PromptSession(color_depth=None if self.r.color else ColorDepth.MONOCHROME)
        return await p.prompt_async(message, default=default)

    async def _confirm(self, message: str) -> bool:
        try:
            ans = await self._ask(message)
        except (KeyboardInterrupt, EOFError):
            return False
        return ans.strip().lower() in ("y", "yes", "是")

    # ------------------------------------------------------------------ 会话

    def _start_new(self, name: str | None = None) -> None:
        """进入新会话。服务端会话等第一条消息时再创建（_ensure_session）。"""
        self.session_id, self.session_name = None, name or ""
        self._pending_name = name or None
        self._auto_title = not name

    async def _ensure_session(self) -> str:
        """当前是还没创建的新会话时，现在创建并激活。"""
        if self.session_id:
            return self.session_id
        try:
            created = await self.ctrl.create_session(self._pending_name)
        except ClientError as e:
            if e.status == 400 and "上限" in str(e):
                raise ClientError("http", f"{e}。可以用 /resume 继续已有会话，或在网页上删除不用的会话", 400)
            raise
        sid = created["session_id"]
        await self.ctrl.activate(sid)
        self.session_id, self.session_name = sid, created.get("name", sid)
        self._pending_name = None
        self.store.set_last_session(sid)
        try:
            await self._refresh_sessions()
        except ClientError:
            pass
        return sid

    async def _auto_name(self, first_message: str) -> None:
        """没起过名的新会话：用第一句话当标题（Claude Code 用小模型生成，这里直接截取，不额外调用模型）。"""
        if not self._auto_title or not self.session_id:
            return
        self._auto_title = False
        title = " ".join(first_message.split())
        title = title if len(title) <= 24 else title[:23] + "…"
        if not title:
            return
        for candidate in [title] + [f"{title} ({n})" for n in range(2, 6)]:
            try:
                await self.ctrl.rename(self.session_id, candidate)
                self.session_name = candidate
                return
            except ClientError as e:
                if e.status != 400:      # 只有重名才换个名字再试；其他错误不影响对话
                    return

    async def _most_recent(self) -> dict | None:
        """-c：本客户端上次用的会话；没有或已删除时，取最近活跃的会话。"""
        last = self.store.last_session
        if last:
            try:
                await self.ctrl.session_detail(last)
                return {"session_id": last}
            except SessionNotFound:
                pass
        sessions = await self._refresh_sessions()
        return sessions[0] if sessions else None

    def _match(self, sessions: list[dict], target: str) -> list[dict]:
        exact = [s for s in sessions if s["session_id"] == target or s["name"] == target]
        if exact:
            return exact
        return [s for s in sessions if s["session_id"].startswith(target)]

    async def _resume_target(self, target: str | None, exit_on_cancel: bool = False) -> dict | None:
        """--resume / /resume：给了名称或 ID 就直接恢复；名字对应多个会话或没给参数时打开选择器。"""
        sessions = await self._refresh_sessions()
        if target:
            hits = self._match(sessions, target)
            if len(hits) == 1:
                return hits[0]
            if not hits:
                self.r.error(f"没有找到会话：{target}")
                return None
            if not exit_on_cancel:
                raise ValueError(f"「{target}」对应多个会话，运行不带参数的 /resume 打开选择器")
        return await self._pick(sessions, query=target or "")

    async def _pick(self, sessions: list[dict], query: str = "") -> dict | None:
        index = 0
        while True:
            result = await pick_session(sessions, self.r.theme, self.r.color, current=self.session_id,
                                        index=index, query=query)
            if result is None:
                return None
            index, query = result.index, result.query
            if result.action == "resume":
                return result.session
            if result.action == "preview":
                await self._preview(result.session)
            elif result.action == "rename":
                await self._rename_from_picker(result.session)
                sessions = await self._refresh_sessions()

    async def _preview(self, session: dict) -> None:
        try:
            detail = await self.ctrl.session_detail(session["session_id"])
        except (ClientError, SessionNotFound) as e:
            self.r.error(f"预览失败：{e}")
            return
        self.r.line(f"── 预览：{session['name']} ──", "accent")
        views.show_history(self.r, detail.get("messages", []), limit=6, compacted=bool(detail.get("summary")))

    async def _rename_from_picker(self, session: dict) -> None:
        try:
            name = (await self._ask(f"  「{session['name']}」重命名为：")).strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not name:
            return
        try:
            await self.ctrl.rename(session["session_id"], name)
            if session["session_id"] == self.session_id:
                self.session_name = name
        except ClientError as e:
            self.r.error(f"重命名失败：{e}")

    async def _switch_to(self, session: dict, show_history: bool) -> bool:
        """激活会话；任何一步失败都保留原来的会话，不猜测成功。"""
        sid = session["session_id"]
        try:
            await self.ctrl.activate(sid)
            detail = await self.ctrl.session_detail(sid)
        except SessionNotFound:
            self.r.error(f"会话不存在：{sid}")
            return False
        except ClientError as e:
            self.r.error(f"切换会话失败：{e}")
            return False
        self.session_id, self.session_name = sid, detail.get("name", sid)
        self.store.set_last_session(sid)
        try:
            await self._refresh_sessions()
        except ClientError:
            pass                       # 只影响参数菜单，不影响切换
        self._pending_name, self._auto_title = None, False   # 已有会话：保留原名，不自动起名
        count = detail.get("token_stats", {}).get("message_count", len(detail.get("messages", [])))
        self.r.blank()
        self.r.line(f"⏺ 会话：{self.session_name}", "accent")
        self.r.dim(f"  ⎿  {sid} · {count} 条消息")
        self.r.blank()
        if show_history and detail.get("messages"):
            # 和 Claude Code 一样整段加载历史；做过压缩的从"对话已压缩"那一行开始
            views.show_history(self.r, detail["messages"], compacted=bool(detail.get("summary")))
        return True

    # ------------------------------------------------------------------ 主循环

    async def _loop(self) -> int:
        while True:
            try:
                text = await self.input.read(default=self.draft)
            except (ExitRequested, EOFError):
                break                 # Ctrl-D / 连按两次 Ctrl-C：退出客户端，不停止服务
            except KeyboardInterrupt:
                continue
            self.draft = ""
            parsed = parse_input(text)
            if parsed.kind == "empty":
                continue
            self.r.user_echo(text.strip("\n"))
            if parsed.kind == "error":
                self.r.error(f"  ⎿  {parsed.text}")
                self.r.blank()
                continue
            if parsed.kind == "chat":
                try:
                    await self._ensure_session()
                except ClientError as e:
                    self.r.error(f"  ⎿  {e}")
                    self.r.blank()
                    continue
                await self.run_turn(parsed.text)
                await self._auto_name(parsed.text)
                continue
            try:
                if parsed.name in ("/compact", "/cache", "/resume"):
                    # 这几个自己要读键盘（确认框、选择器）或走 run_turn，不能再套一层按键接管
                    result = await self._command(parsed.name, parsed.arg)
                else:
                    result = await self._guarded(self._command(parsed.name, parsed.arg))
                if result == "quit":
                    break
            except ClientError as e:
                self.r.error(f"  ⎿  {e}")
            except SessionNotFound as e:
                self.r.error(f"  ⎿  会话不存在：{e}")
            except ValueError as e:
                self.r.error(f"  ⎿  {e}")
            self.r.blank()
        self.r.dim("  已退出客户端；Polaris 服务仍在后台运行。")
        return 0

    # ------------------------------------------------------------------ 一轮对话

    async def run_turn(self, message: str) -> RunState:
        state = RunState(session_id=self.session_id)
        self.last = state
        r = self.r

        async def consume():
            async for ev in self.ctrl.chat(message, self.session_id):
                state.apply(ev)
                if ev.type == TEXT_DELTA:
                    r.text(ev.data["text"])
                elif ev.type == MESSAGE:
                    r.message(ev.data["content"])
                elif ev.type == TOOL_STARTED:
                    r.tool_started(ev.data["call_id"], ev.data["tool"], ev.data.get("args"))
                    r.spinner(f"执行 {ev.data['tool']}")
                elif ev.type == TOOL_FINISHED:
                    call = state.tools[ev.data["call_id"]]
                    r.tool_finished(call.call_id, call.tool, call.result, call.duration)
                    r.spinner("思考中")
                elif ev.type == WARNING:
                    r.dim(f"  ⚠ {ev.data['message']}")
                elif ev.type == FAILED:
                    r.error(f"✗ 服务端错误：{ev.data['error']}")

        async def ticker():
            while True:
                await asyncio.sleep(0.08)
                r.tick()

        task = asyncio.create_task(consume())
        user_cancelled = {"v": False}

        def interrupt():
            if not task.done():
                user_cancelled["v"] = True
                task.cancel()

        draft_before = self.draft
        r.spinner("思考中")
        tick_task = asyncio.create_task(ticker())
        try:
            with self._capture_keys(interrupt):
                try:
                    await task
                except asyncio.CancelledError:
                    if not user_cancelled["v"]:
                        raise
                except ClientError as e:
                    r.spinner(None)
                    r.error(f"✗ {e}")
                    if e.kind == "connect":
                        r.dim("  ⎿  消息没有发出去（连接失败），可以直接重试。")
                    r.blank()
                    return state
        finally:
            tick_task.cancel()
            r.spinner(None)
            r.end_block()
            r.ensure_newline()

        if user_cancelled["v"]:
            state.status = "client_interrupted"
            r.warn("  ⎿  已停止等待。服务端本轮可能已部分执行，已执行的操作不会撤销。")
            if self.server and self.server.fixed_backend:
                r.dim("     服务端会把本轮已发生的部分（含未完成的工具调用）记入会话；可用 /todos /calendar /reminders 核对。")
        elif state.status == STATUS_INTERRUPTED:
            r.warn("  ⎿  连接在本轮结束前断开，服务端可能已部分执行。不会自动重发，请核对后再决定。")
        elif state.status == STATUS_UNKNOWN and not state.has_output:
            r.dim("  ⎿  服务端没有返回文字回复；操作可能已经执行，可用 /todos /calendar /reminders 核对。")
        if self.draft != draft_before:
            r.dim("     （回复期间输入的内容已保留在输入框里）")
        r.blank()
        return state

    async def _guarded(self, coro):
        """执行命令期间也接管按键：提前敲的字进草稿（不回显、回车不提交），Ctrl-C 取消慢请求。"""
        task = asyncio.create_task(coro)
        cancelled = {"v": False}

        def interrupt():
            if not task.done():
                cancelled["v"] = True
                task.cancel()

        with self._capture_keys(interrupt):
            try:
                return await task
            except asyncio.CancelledError:
                if not cancelled["v"]:
                    raise
                self.r.warn("  ⎿  已取消。")
                return None

    @contextmanager
    def _capture_keys(self, on_interrupt):
        """回复进行中接管按键。非终端（管道、测试）时退化为 SIGINT 处理。"""
        loop = asyncio.get_running_loop()
        if not sys.stdin.isatty():
            try:
                loop.add_signal_handler(signal.SIGINT, on_interrupt)
                installed = True
            except (NotImplementedError, RuntimeError, ValueError):
                installed = False
            try:
                yield
            finally:
                if installed:
                    loop.remove_signal_handler(signal.SIGINT)
            return

        inp = create_input()

        def on_keys():
            for kp in inp.read_keys():
                key = kp.key
                if key == Keys.ControlC:
                    on_interrupt()
                elif key in (Keys.ControlH, Keys.Backspace):
                    self.draft = self.draft[:-1]
                elif key == Keys.BracketedPaste:
                    self.draft += kp.data
                elif isinstance(key, Keys):
                    continue          # Enter 等功能键：运行中不发送、不处理
                elif isinstance(key, str) and key.isprintable():
                    self.draft += key

        with inp.raw_mode(), inp.attach(on_keys):
            yield

    # ------------------------------------------------------------------ 命令

    async def _command(self, name: str, arg: str) -> str | None:
        r = self.r
        if name == "/quit":
            return "quit"
        if name == "/help":
            r.line("命令", "accent")
            r.pairs(help_text())
            r.blank()
            r.line("快捷键", "accent")
            r.pairs(SHORTCUTS)
        elif name == "/clear":
            # 和 Claude Code 一样：开始新会话（旧会话保留，/resume 可回去）。只清屏用 Ctrl-L
            previous = self.session_name
            r.clear_screen()
            self._start_new()
            self.last = None
            if previous:
                r.dim(f"  ⎿  已开始新会话；之前的「{previous}」已保留，可用 /resume 回去")
        elif name == "/view":
            if self.last and self.last.has_output:
                r.markdown(self.last.text)
            else:
                r.dim("  ⎿  还没有可显示的回复")
        elif name == "/tools":
            self._show_tools()
        elif name == "/theme":
            if arg not in THEMES:
                r.error(f"  ⎿  用法：/theme {'|'.join(THEMES)}")
            else:
                r.set_theme(arg)
                self.input.theme = arg
                r.ok(f"  ⎿  配色已切换为 {arg}")
        elif name == "/resume":
            chosen = await self._resume_target(arg or None)
            if chosen is not None and chosen["session_id"] != self.session_id:
                await self._switch_to(chosen, show_history=True)
        elif name == "/rename":
            if not arg:
                r.error("  ⎿  用法：/rename <新名称>")
            elif not self.session_id:
                # 还没发过消息的新会话：记下名字，创建时用
                self._pending_name, self._auto_title, self.session_name = arg, False, arg
                r.ok(f"  ⎿  新会话将命名为「{arg}」")
            else:
                await self.ctrl.rename(self.session_id, arg)
                self.session_name, self._auto_title = arg, False
                await self._refresh_sessions()
                r.ok(f"  ⎿  会话已重命名为「{arg}」")
        elif name == "/history":
            if not self.session_id:
                r.dim("  ⎿  新会话，还没有消息")
                return None
            limit = int(arg) if arg.isdigit() else 20
            detail = await self.ctrl.session_detail(self.session_id)
            views.show_history(r, detail.get("messages", []), limit)
        elif name == "/todos":
            views.show_todos(r, await self.ctrl.todos(arg or "all"))
        elif name == "/calendar":
            views.show_calendar(r, await self.ctrl.calendar(arg or None))
        elif name == "/reminders":
            views.show_reminders(r, await self.ctrl.reminders(arg or None))
        elif name == "/status":
            await self._status()
        elif name in ("/compact", "/cache") and not self.session_id:
            r.dim("  ⎿  新会话，还没有消息")
        elif name == "/compact":
            if await self._confirm("  压缩会把较早的对话总结成摘要，会调用模型（可能产生费用）。继续？[y/N] "):
                await self.run_turn("/compact")
        elif name == "/cache":
            await self.run_turn("/cache")
        return None

    def _show_tools(self) -> None:
        if not self.last or not self.last.tools:
            self.r.dim("  ⎿  上一轮没有工具调用")
            return
        for call in self.last.tools.values():
            took = f"{call.duration:.1f}s" if call.duration is not None else "未返回"
            self.r.line(f"⏺ {call.tool}（{took}）", "tool")
            self.r.dim("  ⎿  参数：" + json.dumps(call.args, ensure_ascii=False, indent=2).replace("\n", "\n     "))
            result = call.result if call.result is not None else "（没有收到返回结果）"
            if len(result) > 2000:
                result = result[:2000] + f"…（共 {len(result)} 字，已截断）"
            self.r.dim("     返回：" + result.replace("\n", "\n     "))

    async def _status(self) -> None:
        r = self.r
        info = await self.ctrl.probe()
        self.server = info
        if not info.reachable:
            r.error(f"  ⎿  服务 {self.cfg.url}  ✗ 连不上（{info.error}）")
            return
        rows = [("服务", f"{self.cfg.url}  ● 在线" + ("" if info.fixed_backend else "（修复前的旧版本，请重启服务）"))]
        try:
            self.instance = await self.ctrl.instance()
        except ClientError:
            pass
        rows.append(("模式", describe_instance(self.instance)))
        if self.session_id:
            detail = await self.ctrl.session_detail(self.session_id)
            stats = detail.get("token_stats", {})
            rows += [
                ("会话", f"{detail.get('name')}（{self.session_id}）"),
                ("上下文", f"{stats.get('message_count', '?')} 条消息 · 约 {stats.get('estimated_tokens', '?')} tokens"
                         f"（压缩阈值 {stats.get('compression_trigger', '?')}）"),
            ]
        else:
            rows.append(("会话", "新会话（发出第一条消息后创建）"))
        try:
            st = await self.ctrl.server_status()
            chans = "、".join(f"{c['name']}{'' if c.get('configured') else '(未配置)'}" for c in st.get("channels", []))
            rows.append(("服务端", f"工具 {len(st.get('tools', []))} 个 · 调度任务 {len(st.get('jobs', []))} 个 · 渠道：{chans or '无'}"))
            team = st.get("team")
            if team:
                rows.append(("团队服务", f"已连接：{team['name']}" if team.get("ok")
                             else f"连不上，暂时只有私人数据（{team.get('error')}）"))
        except ClientError as e:
            rows.append(("服务端", f"状态读取失败：{e}"))
        rows.append(("模型", "连通性未测试（/status 不调用模型）"))
        r.pairs(rows, key_style="dim", value_style=None)
