"""标准 SSE 增量解码器。

按 WHATWG 规则处理：任意网络分片、UTF-8 多字节字符被拆在两个分片之间、
CRLF / CR / LF 三种换行、多行 data、注释行（心跳）、空行分帧。
不能把一个 TCP 分片当成一条完整消息。
"""
import codecs
from dataclasses import dataclass

DEFAULT_MAX_FRAME = 1024 * 1024  # 单帧上限，防止异常服务端把内存撑爆


class SSEProtocolError(Exception):
    pass


@dataclass
class SSEFrame:
    event: str | None   # 没有 event 字段时为 None（即默认的 message 事件）
    data: str
    id: str | None = None


class SSEDecoder:
    def __init__(self, max_frame: int = DEFAULT_MAX_FRAME):
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buf = ""
        self._pending_cr = False
        self._max_frame = max_frame
        self._reset_frame()

    def _reset_frame(self):
        self._event: str | None = None
        self._data: list[str] = []
        self._id: str | None = None
        self._frame_size = 0

    def feed(self, chunk: bytes) -> list[SSEFrame]:
        return self._feed_text(self._decoder.decode(chunk))

    def close(self) -> list[SSEFrame]:
        """连接结束。按规范，没有以空行结束的最后一帧被丢弃。"""
        frames = self._feed_text(self._decoder.decode(b"", final=True))
        self._buf = ""
        self._reset_frame()
        return frames

    def _feed_text(self, text: str) -> list[SSEFrame]:
        frames: list[SSEFrame] = []
        if self._pending_cr and text.startswith("\n"):
            # 上一个分片以 \r 结尾，这里的 \n 属于同一个 CRLF
            text = text[1:]
        self._pending_cr = False
        self._buf += text
        while True:
            i = _first_newline(self._buf)
            if i < 0:
                break
            line = self._buf[:i]
            if self._buf[i] == "\r":
                if i + 1 < len(self._buf):
                    step = 2 if self._buf[i + 1] == "\n" else 1
                else:
                    # \r 正好在分片末尾：先按换行处理，记住下个分片开头的 \n 要跳过
                    step = 1
                    self._pending_cr = True
            else:
                step = 1
            self._buf = self._buf[i + step:]
            frame = self._line(line)
            if frame is not None:
                frames.append(frame)
        if len(self._buf) > self._max_frame:
            raise SSEProtocolError("SSE 行超过长度上限")
        return frames

    def _line(self, line: str) -> SSEFrame | None:
        if line == "":
            if not self._data and self._event is None:
                self._reset_frame()
                return None
            frame = SSEFrame(event=self._event, data="\n".join(self._data), id=self._id)
            self._reset_frame()
            return frame
        if line.startswith(":"):
            return None  # 注释 / 心跳
        self._frame_size += len(line)
        if self._frame_size > self._max_frame:
            raise SSEProtocolError("SSE 帧超过长度上限")
        name, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        elif name == "id":
            self._id = value
        # retry 及未知字段按规范忽略
        return None


def _first_newline(s: str) -> int:
    cr, lf = s.find("\r"), s.find("\n")
    if cr < 0:
        return lf
    if lf < 0:
        return cr
    return min(cr, lf)
