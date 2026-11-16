"""personal 服务访问 team 服务的 HTTP 客户端。

- team 服务的现有 REST 接口就是公共数据接口（team 模式下这些接口只返回公共数据）。
- 第一次请求前先确认对方是 team 服务：如果误把 remote.url 指向另一个 personal 服务，
  对方的接口会返回它主人的私人数据，必须拒绝。
- 连不上、超时、5xx 抛 RemoteError（是 DatabaseError 的子类，合并读取时会降级为只显示私人数据）。
"""
import logging
import threading

import httpx

from .mysql import DatabaseError

logger = logging.getLogger("polaris.remote")


class RemoteError(DatabaseError):
    """团队服务不可用或返回错误。message 面向用户。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RemoteClient:
    def __init__(self, base_url: str, timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=False,
                                  trust_env=False, transport=transport)
        self._verified: dict | None = None
        self._lock = threading.Lock()

    @property
    def team_info(self) -> dict | None:
        return self._verified

    def _verify(self) -> None:
        if self._verified is not None:
            return
        with self._lock:
            if self._verified is not None:
                return
            info = self._send("GET", "/api/instance", verify=False)
            if not isinstance(info, dict) or info.get("mode") != "team":
                raise RemoteError(f"remote.url（{self.base_url}）指向的不是团队服务"
                                  f"（对方模式：{(info or {}).get('mode', '未知')}），为避免读到别人的私人数据，已拒绝连接")
            self._verified = info
            logger.info(f"已连接团队服务：{info.get('name')}（{self.base_url}）")

    def _send(self, method: str, path: str, verify: bool = True, **kw):
        if verify:
            self._verify()
        try:
            try:
                resp = self._http.request(method, path, **kw)
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError):
                # 复用的长连接被对方关掉了（team 重启、上一个请求 500 后断开）：幂等请求重试一次
                if method not in ("GET", "PUT", "DELETE"):
                    raise
                resp = self._http.request(method, path, **kw)
        except httpx.TimeoutException:
            raise RemoteError(f"团队服务 {self.base_url} 响应超时")
        except httpx.HTTPError as e:
            self._verified = None          # 下次重新确认：对方可能换了服务
            raise RemoteError(f"连不上团队服务 {self.base_url}（{e}）")
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail") or resp.text
            except ValueError:
                detail = resp.text[:200]
            raise RemoteError(f"团队服务返回错误 {resp.status_code}：{detail}", status=resp.status_code)
        if "application/json" not in resp.headers.get("content-type", ""):
            raise RemoteError(f"团队服务 {path} 返回的不是 JSON，可能版本不匹配")
        return resp.json()

    def get(self, path: str, params: dict | None = None):
        return self._send("GET", path, params=params)

    def post(self, path: str, body: dict | None = None, params: dict | None = None, files=None):
        if files is not None:
            return self._send("POST", path, params=params, files=files)
        return self._send("POST", path, json=body, params=params)

    def put(self, path: str, body: dict):
        return self._send("PUT", path, json=body)

    def delete(self, path: str):
        return self._send("DELETE", path)


_client: RemoteClient | None = None
_client_lock = threading.Lock()


def get_remote() -> RemoteClient | None:
    """personal 模式且配了 remote.url 时返回客户端，否则 None。"""
    global _client
    from .scope import is_team, remote_url
    from src.core.config import config
    url = remote_url()
    if is_team() or not url:
        return None
    if _client is None or _client.base_url != url:
        with _client_lock:
            if _client is None or _client.base_url != url:
                _client = RemoteClient(url, timeout=float(config.get("remote.timeout", 10)))
    return _client


def set_remote(client: RemoteClient | None) -> None:
    """测试用。"""
    global _client
    _client = client
