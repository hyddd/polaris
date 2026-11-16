"""端到端：客户端 → 真实 uvicorn → 真实路由 → 真实编译的 LangGraph（节点是脚本）。

这里验证的是客户端在真实 HTTP/SSE 上的行为，以及它对服务端会话数据造成的实际效果。
"""
import asyncio
import json
import threading

from langchain_core.messages import AIMessage, HumanMessage

from src.cli.application.controller import CHANNEL, Controller
from src.cli.client import PolarisClient
from src.cli.config import load_config
from src.cli.main import main
from src.cli.protocol.events import TERMINAL
from src.message.turn import UNKNOWN_TOOL_RESULT
from tests.test_message._fakes import Script, tool_call


def _ctrl(server):
    return Controller(PolarisClient(load_config(url=server.url)))


def _run(coro):
    return asyncio.run(coro)


async def _collect(server, message, session_id):
    ctrl = _ctrl(server)
    try:
        return [ev async for ev in ctrl.chat(message, session_id)]
    finally:
        await ctrl.client.aclose()


# --- 单次提问（main 入口）---

def test_print_mode_text(live_server, session_mgr, capsys):
    live_server.use(Script([tool_call("todo", "c1", {"action": "list"}), AIMessage(content="你有 0 条待办")],
                           tool_result="[]").build())
    code = main(["--url", live_server.url, "-p", "看看待办"])
    out, err = capsys.readouterr()
    assert code == 6                                   # 旧协议：结果未确认
    assert out == "你有 0 条待办\n"                     # stdout 只有回复正文
    assert "▸ todo" in err and "✓ todo 已返回" in err and "会话：sess_" in err
    # 默认新建独立会话，且服务端历史完整
    sid = err.split("会话：")[1].split("（")[0]
    s = session_mgr.get(sid)
    assert [m.type for m in s.memory.get_messages()] == ["human", "ai", "tool", "ai"]


def test_print_mode_json(live_server, capsys):
    live_server.use(Script([tool_call("todo", "c1", {"action": "list"}), AIMessage(content="好的")]).build())
    code = main(["--url", live_server.url, "-p", "hi", "--output", "json"])
    out, _ = capsys.readouterr()
    obj = json.loads(out)                               # stdout 恰好一个 JSON
    assert code == 6
    assert obj["schema_version"] == 1 and obj["status"] == "unknown" and obj["durability"] == "unverified"
    assert obj["run_id"] is None and obj["effects_state"] == "unknown"   # 不伪造
    assert obj["message"] == "好的"
    assert obj["tool_calls"] == [{"tool": "todo", "args": {"action": "list"}, "result": "工具执行成功"}]


def test_print_mode_ndjson(live_server, capsys):
    live_server.use(Script([AIMessage(content="逐行")]).build())
    code = main(["--url", live_server.url, "-p", "hi", "--output", "ndjson"])
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert code == 6
    assert lines[-1]["type"] == TERMINAL and lines[-1]["status"] == "unknown"
    assert "".join(x.get("text", "") for x in lines if x["type"] == "text_delta") == "逐行"


def test_print_mode_reuses_session(live_server, session_mgr, capsys):
    s = session_mgr.create(name="脚本用")
    live_server.use(Script([AIMessage(content="一"), AIMessage(content="二")]).build())
    main(["--url", live_server.url, "-p", "甲", "--session", s.session_id])
    main(["--url", live_server.url, "-p", "乙", "--session", s.session_id])
    capsys.readouterr()
    assert [m.content for m in s.memory.get_messages()] == ["甲", "一", "乙", "二"]


def test_stdin_mode(live_server, monkeypatch, capsys):
    import io
    live_server.use(Script([AIMessage(content="收到")]).build())
    monkeypatch.setattr("sys.stdin", io.StringIO("从管道来的\n多行消息"))
    assert main(["--url", live_server.url, "--stdin"]) == 6
    assert capsys.readouterr().out == "收到\n"


def test_unknown_session_exit_4(live_server, capsys):
    assert main(["--url", live_server.url, "-p", "hi", "--session", "sess_nope", "--output", "json"]) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_server_down_exit_3(capsys):
    assert main(["--url", "http://127.0.0.1:9", "-p", "hi"]) == 3
    assert "连不上" in capsys.readouterr().err


def test_auth(live_server, monkeypatch, capsys):
    live_server.auth["token"] = "t0ken"
    assert main(["--url", live_server.url, "todo", "list"]) == 3
    assert "认证失败" in capsys.readouterr().err
    monkeypatch.setenv("POLARIS_ADMIN_TOKEN", "t0ken")
    assert main(["--url", live_server.url, "todo", "list"]) == 0


def test_usage_errors(capsys):
    assert main(["-p", "a", "--stdin"]) == 2
    assert main(["--resume", "--session", "x"]) == 2
    assert main(["todo", "list", "-p", "x"]) == 2
    assert main(["-p", "  "]) == 2


# --- 聊天语义 ---

def test_busy_session_reports_failed(live_server, session_mgr):
    from src.core.infra.lock import get_session_lock
    s = session_mgr.active_session("admin")
    lock = get_session_lock(s.session_id)
    lock.acquire()
    try:
        evs = _run(_collect(live_server, "hi", s.session_id))
    finally:
        lock.release()
    assert evs[-1].type == TERMINAL and evs[-1].data["status"] == "failed"
    assert "正在处理中" in evs[-1].data["error"]


def test_confirmation_result_is_shown(live_server, session_mgr):
    """G08：确认/取消的结果没有模型 token，必须作为 message 到达客户端。"""
    s = session_mgr.active_session("admin")
    s.pending_action = {"target_tool": "todo", "params": {"action": "delete", "id": "A"}}
    evs = _run(_collect(live_server, "取消", s.session_id))
    assert any(e.type == "message" and e.data["content"] == "已取消操作。" for e in evs)


def test_cli_channel_does_not_hijack_web_session(live_server, session_mgr):
    """CLI 用 admin:cli，切会话不能改掉网页（admin）记录的当前会话。"""
    web = session_mgr.active_session("admin")
    other = session_mgr.create(name="CLI 用的")
    live_server.use(Script([AIMessage(content="ok")]).build())
    _run(_collect(live_server, "hi", other.session_id))
    assert session_mgr.active_session("admin").session_id == web.session_id
    assert session_mgr.active_session(CHANNEL).session_id == other.session_id


def test_client_cancel_mid_tool_server_keeps_trace(live_server, session_mgr):
    """客户端中断（Ctrl-C）= 断开连接；修复后的服务端要把本轮已发生的部分落盘。"""
    script = Script([tool_call("todo", "c1"), AIMessage(content="不会到这")], block_tools=True)
    live_server.use(script.build())
    s = session_mgr.create(name="中断测试")

    async def scenario():
        task = asyncio.create_task(_collect(live_server, "建个待办", s.session_id))
        await asyncio.to_thread(script.tool_started.wait, 5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    _run(scenario())
    script.tool_release.set()
    # 等服务端发现断开并落盘
    for _ in range(100):
        msgs = s.memory.get_messages()
        if len(msgs) >= 4:
            break
        threading.Event().wait(0.05)
    msgs = s.memory.get_messages()
    assert [m.type for m in msgs] == ["human", "ai", "tool", "ai"]
    assert msgs[2].content in (UNKNOWN_TOOL_RESULT, "工具执行成功")


def test_slash_command_passthrough(live_server, session_mgr):
    s = session_mgr.active_session("admin")
    s.memory.add_message(HumanMessage(content="x"))
    evs = _run(_collect(live_server, "/cache", s.session_id))
    assert any(e.type == "message" for e in evs)
    assert evs[-1].data["status"] == "unknown"


# --- 会话与结构化查询 ---

def test_session_commands(live_server, session_mgr, capsys):
    assert main(["--url", live_server.url, "session", "create", "--name", "新会话", "--output", "json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert session_mgr.get(created["session_id"]).name == "新会话"

    assert main(["--url", live_server.url, "session", "list", "--output", "json"]) == 0
    assert created["session_id"] in [s["session_id"] for s in json.loads(capsys.readouterr().out)]

    assert main(["--url", live_server.url, "session", "show", "sess_nope"]) == 4
    capsys.readouterr()


def test_structured_queries_do_not_call_model(live_server, capsys):
    class Boom:
        def __getattr__(self, name):
            raise AssertionError("查询命令不应调用 agent")
    live_server.use(Boom())
    live_server.todos.create_todo(title="写周报", priority="high", due="2026-11-10")
    t2 = live_server.todos.create_todo(title="已完成的")
    live_server.todos.update_todo(t2.id, {"status": "done"})
    live_server.calendar.create_event(date="2026-11-10", title="评审", time="15:00")

    assert main(["--url", live_server.url, "todo", "list", "--status", "pending", "--output", "json"]) == 0
    assert [t["title"] for t in json.loads(capsys.readouterr().out)] == ["写周报"]

    assert main(["--url", live_server.url, "todo", "list"]) == 0
    out = capsys.readouterr().out
    assert "写周报" in out and "已完成的" in out

    assert main(["--url", live_server.url, "calendar", "list", "--date", "2026-11-10", "--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["title"] == "评审"
    assert main(["--url", live_server.url, "calendar", "list", "--date", "2026-01-01", "--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert main(["--url", live_server.url, "reminder", "list"]) == 0
    assert "没有提醒" in capsys.readouterr().out


def test_doctor_against_live_server(live_server, capsys):
    assert main(["--url", live_server.url, "doctor", "--output", "json"]) == 0
    checks = {c["check"]: c for c in json.loads(capsys.readouterr().out)}
    assert checks["接口"]["level"] == "ok"
    assert checks["服务端版本"]["level"] == "ok"
    assert checks["模型连通性"]["detail"].startswith("未测试")


def test_rename_via_controller(live_server, session_mgr):
    s = session_mgr.create(name="旧")

    async def go():
        ctrl = _ctrl(live_server)
        try:
            await ctrl.rename(s.session_id, "新")
        finally:
            await ctrl.client.aclose()
    _run(go())
    assert s.name == "新"


# --- 服务模式 ---

def test_instance_mode_shown(live_server, monkeypatch):
    from src.cli.application.controller import describe_instance, instance_badge
    from src.core.config import config
    monkeypatch.setitem(config._data, "instance", {"mode": "personal", "name": "张三的 Polaris"})
    monkeypatch.setitem(config._data, "remote", {"url": ""})

    async def go():
        ctrl = _ctrl(live_server)
        try:
            return await ctrl.instance()
        finally:
            await ctrl.client.aclose()
    info = _run(go())
    assert describe_instance(info) == "个人服务 · 张三的 Polaris（只有私人数据，没连团队服务）"
    assert instance_badge(info) == "个人服务·张三的 Polaris"
    monkeypatch.setitem(config._data, "instance", {"mode": "team", "name": "产品组"})
    assert describe_instance(_run(go())) == "团队服务 · 产品组（只读写公共数据）"
    assert describe_instance(None).startswith("未知")
