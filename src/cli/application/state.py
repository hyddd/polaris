"""一次请求（run）的客户端状态。只由事件驱动更新，渲染层只读它。"""
import time
from dataclasses import dataclass, field

from src.cli.protocol.events import (
    Event, TEXT_DELTA, MESSAGE, TOOL_STARTED, TOOL_FINISHED, WARNING, FAILED, TERMINAL,
    STATUS_FAILED,
)


@dataclass
class ToolCall:
    call_id: str
    tool: str
    args: dict
    started_at: float
    finished_at: float | None = None
    result: str | None = None

    @property
    def duration(self) -> float | None:
        return None if self.finished_at is None else self.finished_at - self.started_at


@dataclass
class RunState:
    session_id: str | None = None
    blocks: list[str] = field(default_factory=list)   # 依次出现的文本块（模型回复 / 独立 message）
    tools: dict[str, ToolCall] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    status: str | None = None                         # None 表示还没到终态
    _in_text: bool = False

    def apply(self, ev: Event, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if ev.type == TEXT_DELTA:
            if not self._in_text:
                self.blocks.append("")
                self._in_text = True
            self.blocks[-1] += ev.data["text"]
            return
        self._in_text = False
        if ev.type == MESSAGE:
            # 独立内容块，追加而不是覆盖之前的内容
            self.blocks.append(ev.data["content"])
        elif ev.type == TOOL_STARTED:
            cid = ev.data["call_id"]
            self.tools[cid] = ToolCall(cid, ev.data["tool"], ev.data.get("args") or {}, now)
        elif ev.type == TOOL_FINISHED:
            call = self.tools.get(ev.data["call_id"])
            if call is None:
                call = self.tools[ev.data["call_id"]] = ToolCall(ev.data["call_id"], ev.data["tool"], {}, now)
            call.finished_at = now
            call.result = ev.data.get("result")
        elif ev.type == WARNING:
            self.warnings.append(ev.data["message"])
        elif ev.type == FAILED:
            self.error = ev.data["error"]
        elif ev.type == TERMINAL:
            # error 一旦出现，终态不会被后来的 done 改成非失败
            self.status = STATUS_FAILED if self.error else ev.data["status"]
            self.session_id = ev.data.get("session_id") or self.session_id

    @property
    def text(self) -> str:
        return "\n\n".join(b for b in self.blocks if b.strip())

    @property
    def has_output(self) -> bool:
        return bool(self.text.strip())
