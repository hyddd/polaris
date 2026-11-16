"""应用控制器：会话、聊天、结构化查询。不碰终端光标，不关心输出格式。

终端客户端在服务端用的 channel 是 admin:cli：
- 前缀 admin 让提醒推送走网页会话那条路径（handler 按冒号前的渠道名分发），不会因为找不到 cli 插件而丢；
- 和网页的 admin 分开，CLI 切换会话不会改掉网页"当前会话"的记录。
它只用于路由，不提供权限隔离。
"""
from dataclasses import dataclass
from typing import AsyncIterator

from src.cli.client import ClientError, PolarisClient
from src.cli.protocol.events import Event, TERMINAL, WARNING, STATUS_INTERRUPTED
from src.cli.protocol.legacy import LegacyAdapter
from src.cli.protocol.sse import SSEDecoder, SSEProtocolError

CHANNEL = "admin:cli"

# P0 依赖的现有接口；缺任何一个就无法正常工作
REQUIRED_ENDPOINTS = [
    ("post", "/api/chat/stream"),
    ("get", "/api/sessions"),
    ("post", "/api/sessions"),
    ("get", "/api/sessions/{session_id}"),
    ("post", "/api/sessions/{session_id}/activate"),
    ("get", "/api/data/{data_type}"),
    ("get", "/api/reminders"),
]
# 2026-11-09 后端修复一起加的接口；以此判断服务端是否已经跑着修复后的代码
FIXED_BACKEND_MARKER = ("put", "/api/sessions/{session_id}")


@dataclass
class ServerInfo:
    reachable: bool
    error: ClientError | None = None
    missing: list[str] | None = None
    fixed_backend: bool = False


class SessionNotFound(Exception):
    pass


class Controller:
    def __init__(self, client: PolarisClient):
        self.client = client

    # --- 服务端探测 ---

    async def probe(self) -> ServerInfo:
        """只读探测：GET /openapi.json，看接口是否齐全、是否是修复后的后端。不调用模型。"""
        try:
            spec = await self.client.get("/openapi.json")
        except ClientError as e:
            return ServerInfo(reachable=False, error=e)
        paths = spec.get("paths", {}) if isinstance(spec, dict) else {}

        def has(method, path):
            return method in paths.get(path, {})

        missing = [f"{m.upper()} {p}" for m, p in REQUIRED_ENDPOINTS if not has(m, p)]
        return ServerInfo(reachable=True, missing=missing, fixed_backend=has(*FIXED_BACKEND_MARKER))

    async def server_status(self) -> dict:
        return await self.client.get("/api/status")

    async def instance(self) -> dict | None:
        """服务模式和名字（team / personal）。旧版本服务没有这个接口时返回 None。"""
        try:
            return await self.client.get("/api/instance")
        except ClientError as e:
            if e.status == 404:
                return None
            raise


    # --- 会话 ---

    async def list_sessions(self) -> tuple[list[dict], str | None]:
        data = await self.client.get("/api/sessions", params={"channel": CHANNEL})
        return data.get("sessions", []), data.get("active_session_id")

    async def session_detail(self, session_id: str) -> dict:
        try:
            return await self.client.get(f"/api/sessions/{session_id}")
        except ClientError as e:
            if e.status == 404:
                raise SessionNotFound(session_id)
            raise

    async def create_session(self, name: str | None = None) -> dict:
        body = {"name": name} if name else {}
        created = await self.client.post("/api/sessions", body)
        return created

    async def activate(self, session_id: str) -> None:
        try:
            await self.client.post(f"/api/sessions/{session_id}/activate", params={"channel": CHANNEL})
        except ClientError as e:
            if e.status == 404:
                raise SessionNotFound(session_id)
            raise

    async def resolve_session(self, query: str) -> dict:
        """交互切换用：完整 ID、唯一 ID 前缀或唯一名称。脚本模式不用这个，只认完整 ID。"""
        sessions, _ = await self.list_sessions()
        for s in sessions:
            if s["session_id"] == query:
                return s
        for pred in (lambda s: s["session_id"].startswith(query), lambda s: s["name"] == query,
                     lambda s: query.lower() in s["name"].lower()):
            hits = [s for s in sessions if pred(s)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise ValueError(f"「{query}」匹配到多个会话，请给出更完整的 ID")
        raise SessionNotFound(query)

    async def rename(self, session_id: str, name: str) -> dict:
        try:
            return await self.client.put(f"/api/sessions/{session_id}", {"name": name})
        except ClientError as e:
            if e.status == 405:
                raise ClientError("http", "服务端还是修复前的版本，不支持按 ID 重命名；请先重启服务", 405)
            raise

    # --- 聊天 ---

    async def chat(self, message: str, session_id: str) -> AsyncIterator[Event]:
        """发一条消息，产出内部事件，最后一定以一个 terminal 事件结束。

        还没收到任何字节就失败（连不上、4xx）→ 直接抛 ClientError：请求没有被执行。
        收到部分数据后连接出问题 → 产出 interrupted_unknown 终态：服务端可能已经执行了一部分。
        """
        decoder = SSEDecoder()
        adapter = LegacyAdapter()
        adapter.session_id = session_id
        got_bytes = False
        body = {"message": message, "session_id": session_id, "channel": CHANNEL}
        try:
            async for chunk in self.client.stream("/api/chat/stream", body):
                got_bytes = True
                for frame in decoder.feed(chunk):
                    for ev in adapter.handle(frame):
                        yield ev
            for frame in decoder.close():
                for ev in adapter.handle(frame):
                    yield ev
        except (ClientError, SSEProtocolError) as e:
            if not got_bytes and isinstance(e, ClientError):
                raise
            if not adapter.terminated:
                yield Event(WARNING, {"message": str(e)})
                yield Event(TERMINAL, {"status": STATUS_INTERRUPTED, "session_id": session_id,
                                       "durability": "unverified", "error": str(e)})
            return
        for ev in adapter.finish():
            yield ev

    # --- 结构化查询（不经过模型） ---

    async def todos(self, status: str | None = None) -> list[dict]:
        items = (await self.client.get("/api/data/todos")).get("items", [])
        # 服务端接口不支持按状态过滤，这里在客户端过滤
        if status and status != "all":
            items = [t for t in items if t.get("status") == status]
        return items

    async def calendar(self, date: str | None = None) -> list[dict]:
        items = (await self.client.get("/api/data/calendar")).get("items", [])
        if date:
            items = [e for e in items if e.get("date") == date]
        return sorted(items, key=lambda e: (e.get("date", ""), e.get("time", "")))

    async def reminders(self, status: str | None = None) -> list[dict]:
        items = (await self.client.get("/api/reminders")).get("items", [])
        if status and status != "all":
            items = [r for r in items if r.get("status") == status]
        return sorted(items, key=lambda r: r.get("trigger_time", ""))


def describe_instance(info: dict | None) -> str:
    """一行说明：哪个服务、能读写哪些数据。"""
    if not info:
        return "未知（服务端版本较旧，没有 /api/instance）"
    head = f"{info.get('mode_label', info.get('mode'))} · {info.get('name', 'Polaris')}"
    if info.get("mode") == "team":
        return f"{head}（只读写公共数据）"
    if info.get("public"):
        return f"{head}（私人 + 公共数据，团队服务：{info.get('remote', '')}）"
    return f"{head}（只有私人数据，没连团队服务）"


def instance_badge(info: dict | None) -> str:
    """输入框右下角的简短标识。"""
    if not info:
        return ""
    return f"{info.get('mode_label', info.get('mode'))}·{info.get('name', 'Polaris')}"
