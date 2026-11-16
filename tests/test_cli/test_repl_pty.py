"""交互模式冒烟测试：在伪终端（PTY）里跑真实的 polaris 进程，像人一样敲键盘。

覆盖：首次选择/新建会话、流式回复、Alt+Enter 多行、工具运行中 Ctrl-C、运行中键入的草稿保留、
斜杠命令（查询/拦截）、Ctrl-C 清空输入、Ctrl-D 退出且不影响服务。
"""
import fcntl
import os
import re
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from tests.test_message._fakes import Script, tool_call

ROOT = Path(__file__).resolve().parents[2]
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]|\x1b[=>]|\r")

# 输入框就绪的标志：圆角输入框下方的提示行
READY = "? 快捷键 · / 命令"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="需要 POSIX PTY")


class Term:
    def __init__(self, args, env):
        self.master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 160, 0, 0))
        self.proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env, cwd=ROOT,
                                     start_new_session=True, close_fds=True)
        os.close(slave)
        self.raw = ""
        self.pos = 0   # expect 的查找起点：只在上次匹配之后找

    def _pump(self, timeout):
        r, _, _ = select.select([self.master], [], [], timeout)
        if not r:
            return
        try:
            data = os.read(self.master, 65536).decode("utf-8", "replace")
        except OSError:
            return
        if "\x1b[6n" in data:            # prompt_toolkit 询问光标位置，替终端回答
            os.write(self.master, b"\x1b[1;1R")
        self.raw += data

    @property
    def text(self):
        return ANSI.sub("", self.raw)

    def expect(self, needle, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            i = self.text.find(needle, self.pos)
            if i >= 0:
                self.pos = i + len(needle)
                return
            self._pump(0.05)
        raise AssertionError(f"等不到「{needle}」。最近输出：\n{self.text[-1500:]}")

    def send(self, s, pause=0.15):
        os.write(self.master, s.encode("utf-8"))
        time.sleep(pause)

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(5)
        os.close(self.master)


@pytest.fixture
def term(live_server, tmp_path):
    env = {**os.environ, "TERM": "xterm-256color", "POLARIS_CLI_HOME": str(tmp_path / "cli-home"),
           "PYTHONPATH": str(ROOT), "NO_COLOR": "1"}
    env.pop("POLARIS_ADMIN_TOKEN", None)
    t = Term([sys.executable, "-m", "src.cli", "--url", live_server.url], env)
    yield t
    t.close()


def _env(tmp_path):
    env = {**os.environ, "TERM": "xterm-256color", "POLARIS_CLI_HOME": str(tmp_path / "cli-home"),
           "PYTHONPATH": str(ROOT), "NO_COLOR": "1"}
    env.pop("POLARIS_ADMIN_TOKEN", None)
    return env


def _wait_session(session_mgr, name, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for s in session_mgr.list_sessions():
            if s.name == name:
                return s
        time.sleep(0.05)
    raise AssertionError(f"没有名为「{name}」的会话：{[s.name for s in session_mgr.list_sessions()]}")


def test_interactive_session(term, live_server, session_mgr):
    live_server.use(Script([AIMessage(content="你好呀，我是 Polaris")]).build())
    before = len(session_mgr.list_sessions())

    # 启动：欢迎面板后直接进入新会话（和 Claude Code 一样，不弹选择）
    term.expect("欢迎使用 Polaris")
    term.expect("Ctrl-C 只停止等待")
    term.expect(READY)
    term.expect("会话：新会话")
    assert len(session_mgr.list_sessions()) == before          # 还没发消息：不建会话

    # 第一条消息：创建会话，并用第一句话自动起名
    term.send("你好\r")
    term.expect("> 你好")
    term.expect("⏺ 你好呀，我是 Polaris")
    sess = _wait_session(session_mgr, "你好")
    assert [m.content for m in sess.memory.get_messages()] == ["你好", "你好呀，我是 Polaris"]

    # Alt+Enter 换行：一条消息里带两行
    live_server.use(Script([AIMessage(content="收到两行")]).build())
    term.expect(READY)
    term.send("第一行\x1b\r第二行\r")
    term.expect("收到两行")
    assert sess.memory.get_messages()[2].content == "第一行\n第二行"
    assert sess.name == "你好"                                  # 只在第一条消息后起名

    # 工具：⏺ 工具名(参数) + ⎿ 结果摘要
    live_server.use(Script([tool_call("todo", "c0", {"action": "list"}), AIMessage(content="查完了")],
                           tool_result="[]").build())
    term.expect(READY)
    term.send("看看待办\r")
    term.expect("⏺ todo(action=list)")
    term.expect("⎿  []")
    term.expect("⏺ 查完了")

    # 工具运行中：等待动画；键入草稿（不会被发送），再 Ctrl-C 中断
    script = Script([tool_call("todo", "c1", {"action": "create", "title": "整理报告"}),
                     AIMessage(content="不会显示")], block_tools=True)
    live_server.use(script.build())
    term.expect(READY)
    term.send("帮我建个待办\r")
    term.expect("⏺ todo(action=create title=整理报告)")
    assert script.tool_started.wait(5)
    term.expect("执行 todo…")              # 等待动画
    term.send("草稿内容")
    term.send("\r")                       # 运行中按 Enter 不会发出第二条
    term.send("\x03")                     # Ctrl-C
    term.expect("已停止等待")
    term.expect("保留在输入框")
    term.expect("草稿内容")               # 新的输入框里带着草稿
    script.tool_release.set()

    # 服务端把被中断的这一轮记进了会话（工具调用留痕，不会被下一轮重做）
    for _ in range(100):
        if len(sess.memory.get_messages()) >= 12:
            break
        time.sleep(0.05)
    types = [m.type for m in sess.memory.get_messages()[8:]]
    assert types == ["human", "ai", "tool", "ai"]
    assert script.calls == 1              # 草稿没有被当成新消息发出去

    # Ctrl-C 清空输入框里的草稿
    term.send("\x03")
    # 输入 / 时横线下方列出命令；带参数的命令 Enter 后进入参数菜单
    term.send("/to")
    term.expect("❯ /todos")               # 多个匹配：依次列出，第一个被选中
    term.expect("/tools")
    term.send("\r")
    # 进入参数菜单（prompt_toolkit 只重绘变化的格子，❯ 与上一帧同位置时不会重新输出，所以不匹配 "❯ all"）
    term.expect("in_progress")
    term.expect("已完成")
    term.send("\x1b[B")                   # ↓ 选 pending
    term.send("\r")
    term.expect("> /todos pending")
    term.expect("没有待办")

    # 参数菜单切换配色：/theme → dark
    term.expect(READY)
    term.send("/the\r")
    term.expect("深色背景")
    term.send("\x1b[B\r")
    term.expect("配色已切换为 dark")

    # 输入框是上下两条横线，没有圆角和竖边
    tail = term.text[-3000:]
    assert "╭" not in tail and "╰" not in tail and "│" not in tail
    assert "─" * 40 in tail

    # 空输入按 ? 显示快捷键
    term.expect(READY)
    term.send("?")
    term.expect("空输入连按两次退出")
    term.send("?")

    # 危险命令在本地被拦截；未知命令本地报错，不交给模型
    term.send("/reset\r")
    term.expect("暂不开放")
    term.send("/foo\r")
    term.expect("未知命令 /foo")

    # 空输入连按两次 Ctrl-C 退出
    term.expect(READY)
    term.send("\x03")
    term.expect("再按一次 Ctrl-C 退出")
    term.send("\x03")
    term.expect("已退出客户端")
    assert term.proc.wait(5) == 0


def test_continue_resume_clear_like_claude_code(live_server, session_mgr, tmp_path):
    live_server.use(Script([AIMessage(content=f"第{i}次") for i in range(1, 9)]).build())
    env = _env(tmp_path)
    cli = [sys.executable, "-m", "src.cli", "--url", live_server.url]

    # 1) 新会话，第一句话自动成为会话名
    t = Term(cli, env)
    try:
        t.expect(READY)
        t.send("记住这句\r")
        t.expect("⏺ 第1次")
        t.expect(READY)
        t.send("\x04")                    # Ctrl-D 退出
        t.expect("已退出客户端")
    finally:
        t.close()
    _wait_session(session_mgr, "记住这句")

    # 2) -n 指定名称的新会话
    t = Term(cli + ["-n", "周报会话"], env)
    try:
        t.expect("会话：周报会话")
        t.send("写周报\r")
        t.expect("⏺ 第2次")
        t.expect(READY)
        t.send("\x04")
        t.expect("已退出客户端")
    finally:
        t.close()
    _wait_session(session_mgr, "周报会话")

    # 3) -c：继续最近的会话（就是刚才的周报会话），整段历史加载出来
    t = Term(cli + ["-c"], env)
    try:
        t.expect("会话：周报会话")
        t.expect("> 写周报")
        t.expect("⏺ 第2次")
        t.expect(READY)
        t.send("\x04")
        t.expect("已退出客户端")
    finally:
        t.close()

    # 4) --resume：会话选择器。输入文字搜索 → 空格预览 → Enter 恢复
    t = Term(cli + ["--resume"], env)
    try:
        t.expect("恢复会话")
        t.expect("周报会话")
        t.send("记住")                     # 直接输入文字 = 搜索
        t.expect("搜索：记住")
        t.send(" ")                        # 搜索模式下空格是普通字符；先退出搜索再预览
        t.send("\x1b")                     # Esc 退出搜索
        time.sleep(0.3)
        t.send("\x1b[B")                   # 第二个：记住这句（第一个是最近的周报会话）
        t.send(" ")                        # 空格预览
        t.expect("预览：记住这句")
        t.expect("恢复会话")               # 预览后回到选择器
        t.send("\r")
        t.expect("会话：记住这句")
        t.expect("> 记住这句")
        t.expect(READY)

        # 5) /clear：开新会话，旧会话保留
        t.send("/clear\r")
        t.expect("已开始新会话")
        t.expect("会话：新会话")

        # 6) /resume <名称>：直接恢复
        t.send("/resume 周报会话\r")
        t.expect("会话：周报会话")
        t.expect("> 写周报")
        t.expect(READY)
        t.send("\x04")
        t.expect("已退出客户端")
    finally:
        t.close()

    # 7) --resume <名称> 直接恢复；找不到时报错退出
    t = Term(cli + ["--resume", "记住这句"], env)
    try:
        t.expect("会话：记住这句")
        t.expect(READY)
        t.send("\x04")
        t.expect("已退出客户端")
    finally:
        t.close()
    t = Term(cli + ["--resume", "不存在的会话"], env)
    try:
        t.expect("没有找到会话：不存在的会话")
        assert t.proc.wait(5) == 4
    finally:
        t.close()
