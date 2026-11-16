"""命令白名单、配置、本地状态、终端过滤、渲染。"""
import io
import json
import os
import stat

import pytest

from src.cli.application.commands import parse_input
from src.cli.config import ConfigError, load_config, normalize_url
from src.cli.storage import StateStore
from src.cli.ui.render import Renderer, summarize_args
from src.cli.ui.sanitize import sanitize


# --- 命令解析 ---

@pytest.mark.parametrize("line,kind", [
    ("你好", "chat"), ("  ", "empty"), ("/help", "command"), ("/todos done", "command"),
    ("/unknown", "error"), ("/reset", "error"), ("/cleanup", "error"), ("/reload", "error"),
])
def test_parse_kinds(line, kind):
    assert parse_input(line).kind == kind


def test_double_slash_escapes_but_not_into_server_command():
    assert parse_input("//etc/hosts 是什么").text == "/etc/hosts 是什么"
    blocked = parse_input("//reset")
    assert blocked.kind == "error" and "/reset" in blocked.text


def test_multiline_chat_preserved():
    assert parse_input("第一行\n第二行").text == "第一行\n第二行"


# --- 配置 ---

def test_defaults():
    cfg = load_config()
    assert cfg.url == "http://127.0.0.1:8700" and cfg.token is None and cfg.profile == "local"


def test_precedence_flag_env_file(tmp_path, monkeypatch):
    f = tmp_path / "c.yaml"
    f.write_text('default_profile: home\nprofiles:\n  home:\n    url: "http://127.0.0.1:9001"\n'
                 'ui:\n  theme: dark\n', encoding="utf-8")
    assert load_config(config_path=str(f)).url == "http://127.0.0.1:9001"
    monkeypatch.setenv("POLARIS_URL", "http://localhost:9002/")
    assert load_config(config_path=str(f)).url == "http://localhost:9002"
    assert load_config(config_path=str(f), url="http://127.0.0.1:9003").url == "http://127.0.0.1:9003"
    assert load_config(config_path=str(f)).theme == "dark"
    assert load_config(config_path=str(f), theme="light").theme == "light"


def test_unknown_profile_errors(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text('profiles:\n  a:\n    url: "http://127.0.0.1:1"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=str(f), profile="b")


def test_remote_requires_https():
    with pytest.raises(ConfigError):
        load_config(url="http://192.168.1.10:8700")
    cfg = load_config(url="https://polaris.example.com")
    assert any("凭据" in w for w in cfg.warnings)


def test_token_from_env_and_file(tmp_path, monkeypatch):
    tf = tmp_path / "tok"
    tf.write_text("secret-file\n", encoding="utf-8")
    os.chmod(tf, 0o644)
    cfg = load_config(token_file=str(tf))
    assert cfg.token == "secret-file" and cfg.token_source.startswith("file:")
    assert any("chmod 600" in w for w in cfg.warnings)
    monkeypatch.setenv("POLARIS_ADMIN_TOKEN", "secret-env")
    assert load_config(token_file=str(tf)).token == "secret-env"


def test_bad_url_and_bad_config_file(tmp_path):
    with pytest.raises(ConfigError):
        normalize_url("ftp://x")
    f = tmp_path / "bad.yaml"
    f.write_text("ui: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=str(f))
    f.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=str(f))


# --- 本地状态 ---

def test_state_store_roundtrip_and_permissions(tmp_path):
    p = tmp_path / "home" / "state.json"
    s = StateStore(p, "local|http://127.0.0.1:8700")
    assert s.last_session is None
    s.set_last_session("sess_1")
    assert StateStore(p, "local|http://127.0.0.1:8700").last_session == "sess_1"
    assert StateStore(p, "other|http://x").last_session is None
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o700
    assert "sess_1" in p.read_text() and "message" not in p.read_text()   # 不存聊天内容


def test_corrupt_state_is_kept_aside(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{broken", encoding="utf-8")
    s = StateStore(p, "k")
    assert s.warning and s.last_session is None
    kept = list(tmp_path.glob("state.json.corrupt-*"))
    assert kept and kept[0].read_text() == "{broken"


# --- 终端过滤 ---

@pytest.mark.parametrize("evil", [
    "\x1b]0;被改了的标题\x07",          # OSC 改窗口标题
    "\x1b]52;c;ZXZpbA==\x07",          # OSC 52 写剪贴板
    "\x1b[2J\x1b[H",                   # 清屏 + 光标归位
    "\x1b[31m",                        # 颜色
    "\x9b2J",                          # 8 位 CSI
    "\x1bP+q\x1b\\",                   # DCS
    "\x07\x08\x00",                    # 响铃、退格、NUL
])
def test_sanitize_strips_control_sequences(evil):
    out = sanitize(f"前{evil}后")
    assert out == "前后"


def test_sanitize_keeps_text_newlines_tabs_and_cjk():
    assert sanitize("a\tb\r\n中文😀\n") == "a\tb\n中文😀\n"


# --- 渲染 ---

def test_renderer_plain_when_not_tty_and_no_color(monkeypatch):
    buf = io.StringIO()
    r = Renderer(buf, color="auto")
    r.user_echo("你好\n第二行")
    r.text("回复\x1b[31m内容\n续行")
    r.flush()
    r.tool_started("c", "todo", {"action": "list"})
    r.tool_finished("c", "todo", '[{"id": 1}]\n[{"id": 2}]', 0.25)
    r.spinner("思考中")
    r.tick()                              # 非终端：不画动画
    r.spinner(None)
    out = buf.getvalue()
    assert "\x1b" not in out
    assert out == ("> 你好\n  第二行\n"
                   "⏺ 回复内容\n  续行\n"
                   "⏺ todo(action=list)\n"
                   '  ⎿  [{"id": 1}]  …共 2 行 · 0.2s\n')


def test_message_block_indents_continuation_lines():
    buf = io.StringIO()
    r = Renderer(buf, color="never")
    r.message("第一行\n\n第三行")
    assert buf.getvalue() == "⏺ 第一行\n\n  第三行\n"


def test_spinner_draws_only_at_line_start_and_is_erased_before_output(monkeypatch):
    import src.cli.ui.render as render_mod

    class TTY(io.StringIO):
        def isatty(self):
            return True

    buf = TTY()
    r = Renderer(buf, color="never")
    r.spinner("思考中")
    r._last_output = 0                     # 假装很久没有输出
    r.tick()
    assert "思考中… (" in buf.getvalue() and "Ctrl-C 中断" in buf.getvalue()
    r.text("答")
    r.flush()
    assert buf.getvalue().endswith("\r\x1b[2K⏺ 答")   # 先擦掉动画行再写回复
    before = buf.getvalue()
    r._last_output = 0
    r.tick()                               # 光标在一行中间：不画动画
    assert buf.getvalue() == before
    assert render_mod.SPINNER_DELAY > 0


def test_summarize_result():
    from src.cli.ui.render import summarize_result
    assert summarize_result(None) == "（没有收到结果）"
    assert summarize_result("  \n") == "（空）"
    assert summarize_result("x" * 100).endswith("…")
    assert summarize_result("\x1b]0;t\x07ok") == "ok"


def test_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert Renderer(io.StringIO(), color="auto").color is False
    assert Renderer(io.StringIO(), color="always").color is True


def test_summarize_args_truncates_and_sanitizes():
    s = summarize_args({"title": "x" * 100, "evil": "\x1b]0;t\x07ok"}, limit=40)
    assert len(s) <= 40 and "\x1b" not in s
    assert summarize_args({"date": "2026-11-09", "n": 3}) == "date=2026-11-09 n=3"
    assert summarize_args(None) == ""


def test_auto_theme_never_uses_palette_greys():
    """auto 配色不能用亮黑/黑/白/写死的灰：很多终端主题（如 Solarized Dark，COLORFGBG=12;8）的背景就是这些颜色。"""
    from src.cli.ui.input_box import PT_STYLES
    from src.cli.ui.render import PALETTES
    banned = ("bright_black", "ansibrightblack", "black", "white", "grey", "gray", "#")
    for name, value in list(PALETTES["auto"].items()) + list(PT_STYLES["auto"].items()):
        assert not any(b in value for b in banned), f"auto 配色 {name}={value!r}"


def test_auto_theme_secondary_text_is_faint_default_fg():
    import re
    buf = io.StringIO()
    r = Renderer(buf, color="always", theme="auto")
    r.user_echo("你好")
    r.tool_finished("c", "todo", "[]", 0.1)
    codes = set(re.findall(r"\x1b\[([0-9;]*)m", buf.getvalue()))
    assert "2" in codes                                    # 暗淡（SGR 2）
    assert not any(re.search(r"(^|;)(90|30|37|97)(;|$)", c) for c in codes)


def test_default_config_file_location(tmp_path, monkeypatch):
    """不设 POLARIS_CLI_HOME 时：配置在 config/cli.yaml，状态在 data/cli/；设置后都在该目录。"""
    import src.cli.config as cli_config
    monkeypatch.delenv("POLARIS_CLI_HOME", raising=False)
    monkeypatch.setattr(cli_config, "PROJECT_ROOT", tmp_path)
    assert cli_config.default_config_file() == tmp_path / "config" / "cli.yaml"
    assert cli_config.cli_home() == tmp_path / "data" / "cli"
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cli.yaml").write_text("ui:\n  theme: light\n")
    assert load_config().theme == "light"
    monkeypatch.setenv("POLARIS_CLI_HOME", str(tmp_path / "h"))
    assert cli_config.default_config_file() == tmp_path / "h" / "cli.yaml"


def test_cli_yaml_example_is_valid_and_matches_defaults():
    """入库的示例能被正常读取，且写的都是默认值：复制后行为不变。"""
    from pathlib import Path
    example = Path(__file__).resolve().parents[2] / "config" / "cli.yaml.example"
    cfg = load_config(config_path=str(example))
    assert (cfg.profile, cfg.url, cfg.theme, cfg.color, cfg.persist_history) == \
        ("local", "http://127.0.0.1:8700", "auto", "auto", False)
    assert (cfg.connect_timeout, cfg.read_timeout, cfg.token) == (5.0, 300.0, None)
    assert load_config(config_path=str(example), profile="team").url == "http://127.0.0.1:8710"
