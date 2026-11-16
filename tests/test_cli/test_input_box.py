"""输入框按键行为：两级菜单（命令 → 参数）、Tab/Enter、过滤、快捷键面板、退出。

用 prompt_toolkit 的管道输入喂真实按键序列，不需要终端。
"""
import asyncio

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from src.cli.ui.input_box import ExitRequested, InputBox

UP, DOWN, TAB, ENTER, CTRL_C = "\x1b[A", "\x1b[B", "\t", "\r", "\x03"


def _box(provider=None):
    return InputBox(InMemoryHistory(), theme="auto", color=False, right_hint=lambda: "会话：x",
                    arg_provider=provider)


def type_and_read(keys: str, box: InputBox | None = None, default: str = "") -> str:
    box = box or _box()

    async def run():
        with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
            inp.send_text(keys)
            return await asyncio.wait_for(box.read(default), 5)
    return asyncio.run(run())


def test_plain_text_and_alt_enter_newline():
    assert type_and_read("你好" + ENTER) == "你好"
    assert type_and_read("第一行\x1b\r第二行" + ENTER) == "第一行\n第二行"


def test_command_without_args_executes_on_enter():
    # /sta 只匹配 /status（无参数）→ Enter 直接执行
    assert type_and_read("/sta" + ENTER) == "/status"
    # 已完整输入无参数命令：不弹菜单，Enter 原样提交
    assert type_and_read("/status" + ENTER) == "/status"


def test_command_with_choices_opens_second_level():
    # /the → Enter 选中 /theme（有参数）→ 进入参数菜单，↓ 选 dark，Enter 执行
    assert type_and_read("/the" + ENTER + DOWN + ENTER) == "/theme dark"
    # 第一项就是 auto
    assert type_and_read("/the" + ENTER + ENTER) == "/theme auto"


def test_tab_only_completes_does_not_submit():
    # Tab 补全到参数级，再 Tab 补全参数，最后 Enter 提交
    assert type_and_read("/tod" + TAB + DOWN + TAB + ENTER) == "/todos pending"


def test_arrow_navigation_wraps_and_filters_by_typing():
    # /todos 参数：all pending in_progress done；↑ 从第一项回绕到最后一项
    assert type_and_read("/todos " + UP + ENTER) == "/todos done"
    # 输入过滤：按说明里的中文也能过滤
    assert type_and_read("/todos 进行" + ENTER) == "/todos in_progress"


def test_first_level_lists_multiple_matches_in_order():
    box = _box()
    box.buffer.text = "/to"
    assert [i.label for i in box.items()] == ["/todos", "/tools"]
    box.buffer.text = "/"
    assert len(box.items()) == 8               # 最多显示 8 项


def test_dynamic_args_from_provider():
    calls = []

    def provider(name):
        calls.append(name)
        return [("", "打开会话选择器"), ("sess_a", "日常安排 · 3 条消息"), ("sess_b", "工作 · 10 条消息")] \
            if name == "/resume" else []

    box = _box(provider)
    assert type_and_read("/resume " + DOWN + DOWN + ENTER, box) == "/resume sess_b"
    assert type_and_read("/resume 工作" + ENTER, _box(provider)) == "/resume sess_b"
    assert type_and_read("/res" + ENTER + ENTER, _box(provider)) == "/resume"     # 第一项：打开选择器
    assert "/resume" in calls


def test_empty_value_choice_means_no_argument():
    provider = lambda name: [("", "全部日程"), ("2026-11-10", "明天")]
    assert type_and_read("/calendar " + ENTER, _box(provider)) == "/calendar"
    assert type_and_read("/calendar " + DOWN + ENTER, _box(provider)) == "/calendar 2026-11-10"


def test_unknown_value_is_submitted_as_typed():
    # 不在选项里的值（手输日期、完整会话 ID）照样提交，由命令自己校验
    provider = lambda name: [("", "全部日程")]
    assert type_and_read("/calendar 2026-12-01" + ENTER, _box(provider)) == "/calendar 2026-12-01"


def test_text_argument_shows_placeholder_and_submits_typed():
    box = _box()
    box.buffer.text = "/rename "
    assert "输入新名称" in box._placeholder()
    assert box.items() == []
    assert type_and_read("/ren" + ENTER + "新名字" + ENTER) == "/rename 新名字"


def test_double_slash_escape_has_no_menu():
    box = _box()
    box.buffer.text = "//etc"
    assert box.items() == []
    assert type_and_read("//etc/hosts" + ENTER) == "//etc/hosts"


def test_question_mark_toggles_shortcuts_only_when_empty():
    box = _box()

    async def run():
        with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
            inp.send_text("?")
            task = asyncio.create_task(box.read())
            await asyncio.sleep(0.2)
            shown = box._show_shortcuts
            inp.send_text("x?" + ENTER)            # 开始输入后 ? 就是普通字符
            return shown, await asyncio.wait_for(task, 5)

    shown, text = asyncio.run(run())
    assert shown is True
    assert text == "x?"


def test_ctrl_c_clears_then_double_press_exits():
    assert type_and_read("要清掉的" + CTRL_C + "留下" + ENTER) == "留下"
    with pytest.raises(ExitRequested):
        type_and_read(CTRL_C + CTRL_C)


def test_draft_is_restored_as_default():
    assert type_and_read("补充" + ENTER, default="草稿") == "草稿补充"
