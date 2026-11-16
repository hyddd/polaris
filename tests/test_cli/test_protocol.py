"""协议层：SSE 解码 + 旧协议适配 + run 状态。"""
import json

import pytest

from src.cli.application.state import RunState
from src.cli.protocol.events import (
    TEXT_DELTA, MESSAGE, TOOL_STARTED, TOOL_FINISHED, WARNING, FAILED, TERMINAL,
    STATUS_UNKNOWN, STATUS_FAILED, STATUS_INTERRUPTED,
)
from src.cli.protocol.legacy import LegacyAdapter
from src.cli.protocol.sse import SSEDecoder, SSEProtocolError


def _decode_all(chunks):
    d = SSEDecoder()
    frames = []
    for c in chunks:
        frames += d.feed(c)
    return frames + d.close()


SAMPLE = (
    'data: {"token":"今天还有两项待办"}\n\n'
    'event: tool_call\ndata: {"tool":"todo","args":{"action":"list"},"call_id":"c1"}\n\n'
    'event: tool_result\ndata: {"tool":"todo","result":"[]","call_id":"c1"}\n\n'
    'event: done\ndata: {"session_id":"s1"}\n\n'
).encode("utf-8")


def test_decode_whole_stream():
    frames = _decode_all([SAMPLE])
    assert [f.event for f in frames] == [None, "tool_call", "tool_result", "done"]
    assert json.loads(frames[0].data) == {"token": "今天还有两项待办"}


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7])
def test_decode_arbitrary_chunking_splits_utf8(size):
    """任意分片（包括把一个中文字符的 3 个字节拆开）结果都一样。"""
    chunks = [SAMPLE[i:i + size] for i in range(0, len(SAMPLE), size)]
    assert _decode_all(chunks) == _decode_all([SAMPLE])


def test_crlf_and_cr_line_endings():
    crlf = SAMPLE.replace(b"\n", b"\r\n")
    cr = SAMPLE.replace(b"\n", b"\r")
    assert _decode_all([crlf]) == _decode_all([SAMPLE])
    assert _decode_all([cr]) == _decode_all([SAMPLE])
    # \r 和 \n 被拆在两个分片里
    i = crlf.index(b"\r\n")
    assert _decode_all([crlf[:i + 1], crlf[i + 1:]]) == _decode_all([SAMPLE])


def test_multiline_data_comments_and_space_handling():
    raw = b": heartbeat\n\nevent: message\ndata: line1\ndata:line2\ndata:  two-spaces\nid: 7\nretry: 100\n\n"
    frames = _decode_all([raw])
    assert len(frames) == 1
    assert frames[0].event == "message"
    assert frames[0].data == "line1\nline2\n two-spaces"
    assert frames[0].id == "7"


def test_trailing_frame_without_blank_line_is_dropped():
    assert _decode_all([b'data: {"token":"x"}\n']) == []


def test_frame_size_limit():
    d = SSEDecoder(max_frame=100)
    with pytest.raises(SSEProtocolError):
        d.feed(b"data: " + b"x" * 200 + b"\n")
    with pytest.raises(SSEProtocolError):
        SSEDecoder(max_frame=100).feed(b"data: " + b"y" * 200)   # 没有换行也不能无限累积


def _adapt(raw: bytes):
    a = LegacyAdapter()
    events = []
    for f in _decode_all([raw]):
        events += a.handle(f)
    return events + a.finish()


def test_adapter_maps_events():
    evs = _adapt(SAMPLE)
    assert [e.type for e in evs] == [TEXT_DELTA, TOOL_STARTED, TOOL_FINISHED, TERMINAL]
    assert evs[-1].data["status"] == STATUS_UNKNOWN          # 旧协议 done ≠ 已提交
    assert evs[-1].data["durability"] == "unverified"
    assert evs[-1].data["session_id"] == "s1"


def test_error_then_done_stays_failed():
    raw = (b'event: error\ndata: {"error":"\xe5\xbf\x99","traceback":"secret"}\n\n'
           b'event: done\ndata: {"session_id":"s"}\n\n')
    evs = _adapt(raw)
    assert [e.type for e in evs] == [FAILED, TERMINAL]
    assert evs[-1].data["status"] == STATUS_FAILED
    assert "traceback" not in evs[0].data


def test_eof_without_done_is_interrupted():
    evs = _adapt(b'data: {"token":"\xe5\x8d\x8a"}\n\n')
    assert evs[-1].type == TERMINAL and evs[-1].data["status"] == STATUS_INTERRUPTED


def test_unknown_event_and_bad_json_are_warnings():
    evs = _adapt(b"event: node\ndata: {}\n\ndata: not-json\n\nevent: done\ndata: {}\n\n")
    assert [e.type for e in evs] == [WARNING, WARNING, TERMINAL]


def test_events_after_done_are_warnings():
    a = LegacyAdapter()
    frames = _decode_all([b'event: done\ndata: {}\n\ndata: {"token":"late"}\n\n'])
    out = [e for f in frames for e in a.handle(f)]
    assert out[-1].type == WARNING
    assert a.finish() == []


def test_missing_call_id_degrades_to_order():
    raw = (b'event: tool_call\ndata: {"tool":"a"}\n\nevent: tool_result\ndata: {"tool":"a","result":"1"}\n\n'
           b'event: done\ndata: {}\n\n')
    evs = _adapt(raw)
    assert evs[0].data["call_id"] == evs[1].data["call_id"]


def test_run_state_blocks_and_tools():
    raw = (b'data: {"token":"\xe5\x89\x8d"}\n\n'
           b'event: tool_call\ndata: {"tool":"todo","args":{"a":1},"call_id":"c"}\n\n'
           b'event: tool_result\ndata: {"tool":"todo","result":"ok","call_id":"c"}\n\n'
           b'data: {"token":"\xe5\x90\x8e"}\n\n'
           b'event: message\ndata: {"content":"\xe5\x9d\x97"}\n\n'
           b'event: done\ndata: {"session_id":"s"}\n\n')
    st = RunState()
    t = 0.0
    for e in _adapt(raw):
        t += 1
        st.apply(e, now=t)
    assert st.blocks == ["前", "后", "块"]          # message 追加为独立块，不覆盖前面的内容
    assert st.tools["c"].result == "ok" and st.tools["c"].duration == 1.0
    assert st.status == STATUS_UNKNOWN and st.session_id == "s"
