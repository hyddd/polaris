"""非交互模式：单次聊天（-p / --stdin）和结构化命令的输出。

stdout 只放结果（text：回复正文；json：恰好一个对象；ndjson：每行一个事件，最后一行是终态），
进度、工具摘要、会话 ID、警告都写 stderr。

旧聊天协议收到 done 也只代表"回答接收结束、业务提交未确认"，所以单次聊天成功时退出码是 6，
不是 0。等服务端提供可确认的提交语义（设计文档 P1）后才能返回 0。
"""
import asyncio
import json
import sys
import time

from src.cli.application.controller import Controller, SessionNotFound
from src.cli.application.state import RunState
from src.cli.client import ClientError
from src.cli.protocol.events import (
    TEXT_DELTA, MESSAGE, TOOL_STARTED, TOOL_FINISHED, WARNING, FAILED, TERMINAL,
    STATUS_UNKNOWN, STATUS_FAILED, STATUS_CLIENT_INTERRUPTED,
)
from src.cli.ui.render import Renderer
from src.cli.ui.sanitize import sanitize

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONNECTION = 3
EXIT_SERVER = 4
EXIT_NEEDS_CONFIRMATION = 5
EXIT_UNKNOWN = 6
EXIT_INTERRUPTED = 130

STATUS_EXIT = {
    STATUS_UNKNOWN: EXIT_UNKNOWN,
    STATUS_FAILED: EXIT_SERVER,
    STATUS_CLIENT_INTERRUPTED: EXIT_INTERRUPTED,
}


def result_object(state: RunState, status: str, error: str | None = None) -> dict:
    """单次调用的最终对象。v1 不伪造 run ID、资源 ID 或已提交状态。"""
    return {
        "schema_version": 1,
        "status": status,
        "session_id": state.session_id,
        "run_id": None,
        "message": state.text,
        "tool_calls": [{"tool": t.tool, "args": t.args, "result": t.result} for t in state.tools.values()],
        "resources": [],
        "effects_state": "unknown",
        "durability": "unverified",
        "warnings": state.warnings,
        "error": error if error is not None else state.error,
    }


def exit_for(status: str) -> int:
    return STATUS_EXIT.get(status, EXIT_UNKNOWN)


def _session_name() -> str:
    return time.strftime("cli %Y-%m-%d %H:%M:%S")


async def prepare_session(ctrl: Controller, session_id: str | None, err: Renderer,
                          new_name: str | None = None) -> str:
    """单次调用的会话：给了会话 ID（-c / -r）就用它；否则新建一个独立会话，不污染正在用的会话。"""
    if session_id:
        await ctrl.session_detail(session_id)   # 不存在抛 SessionNotFound
        return session_id
    try:
        created = await ctrl.create_session(new_name or _session_name())
    except ClientError as e:
        if e.status == 400:
            raise ClientError("http", f"{e}。可以用 -c 或 --resume <ID> 复用已有会话", 400)
        raise
    return created["session_id"]


async def run_once(ctrl: Controller, message: str, session_id: str | None, output: str,
                   out=None, err_stream=None, color: str = "auto", new_name: str | None = None) -> int:
    out = out or sys.stdout
    err = Renderer(err_stream or sys.stderr, color=color)
    state = RunState()

    def emit_ndjson(obj: dict) -> None:
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out.flush()

    def fail(code: int, status: str, msg: str) -> int:
        if output == "json":
            out.write(json.dumps(result_object(state, status, msg), ensure_ascii=False, indent=2) + "\n")
        elif output == "ndjson":
            emit_ndjson({"type": TERMINAL, "status": status, "session_id": state.session_id, "error": msg})
        err.error(msg)
        return code

    try:
        state.session_id = await prepare_session(ctrl, session_id, err, new_name)
    except SessionNotFound as e:
        return fail(EXIT_SERVER, STATUS_FAILED, f"会话不存在：{e}")
    except ClientError as e:
        return fail(e.exit_code, STATUS_FAILED, str(e))
    if not session_id:
        err.dim(f"会话：{state.session_id}（新建；用 --resume {state.session_id} 可继续这个会话）")

    printed_text = False
    try:
        async for ev in ctrl.chat(message, state.session_id):
            state.apply(ev)
            if output == "ndjson":
                emit_ndjson(ev.to_dict())
            elif output == "text":
                if ev.type == TEXT_DELTA:
                    out.write(sanitize(ev.data["text"]))
                    out.flush()
                    printed_text = True
                elif ev.type == MESSAGE:
                    if printed_text:
                        out.write("\n\n")
                    out.write(sanitize(ev.data["content"]))
                    out.flush()
                    printed_text = True
                elif ev.type == TOOL_STARTED:
                    err.dim(f"  ▸ {ev.data['tool']}")
                elif ev.type == TOOL_FINISHED:
                    call = state.tools.get(ev.data["call_id"])
                    took = f" {call.duration:.1f}s" if call and call.duration is not None else ""
                    err.dim(f"  ✓ {ev.data['tool']} 已返回{took}")
                elif ev.type == WARNING:
                    err.warn(f"警告：{ev.data['message']}")
                elif ev.type == FAILED:
                    err.error(f"服务端错误：{ev.data['error']}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        # asyncio.run 收到 SIGINT 时取消主任务，这里看到的是 CancelledError
        status = STATUS_CLIENT_INTERRUPTED
        state.status = status
        if output == "ndjson":
            emit_ndjson({"type": TERMINAL, "status": status, "session_id": state.session_id})
        elif output == "json":
            out.write(json.dumps(result_object(state, status), ensure_ascii=False, indent=2) + "\n")
        else:
            out.write("\n")
        err.warn("已中断等待。服务端本轮可能已部分执行，已执行的操作不会撤销。")
        return EXIT_INTERRUPTED
    except ClientError as e:
        return fail(e.exit_code, STATUS_FAILED, str(e))

    status = state.status or STATUS_UNKNOWN
    if output == "json":
        out.write(json.dumps(result_object(state, status), ensure_ascii=False, indent=2) + "\n")
    elif output == "text":
        if printed_text:
            out.write("\n")
        if not state.has_output and status == STATUS_UNKNOWN:
            err.warn("服务端没有返回文字回复；操作可能已经执行，可用 polaris todo list 等命令核对。")
    if status == STATUS_UNKNOWN:
        err.dim("回答接收结束；旧聊天协议不提供提交确认，退出码 6 表示「结果未确认」。")
    elif status == STATUS_FAILED:
        if output != "text":      # text 模式下错误已在流里打印过
            err.error(f"失败：{state.error}")
    else:
        err.warn("连接在本轮结束前断开，服务端可能已部分执行；请核对后再决定是否重发（不会自动重发）。")
    return exit_for(status)


def print_json(obj, out=None) -> None:
    out = out or sys.stdout
    out.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
