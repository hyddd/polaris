"""HTTP 传输层。只负责请求、超时、错误分类，不理解业务。

- GET 可以有界重试（连接失败时）；POST/PUT 一律不自动重发，避免重复创建或重复执行。
- Authorization 只放在请求头；不跟随重定向（httpx 默认），避免把 token 带到别的 origin。
- 服务端有 SPA 兜底路由：不存在的 GET 可能返回 200 的 HTML，所以必须校验 Content-Type。
"""
import asyncio
from typing import Any, AsyncIterator

import httpx

from .config import ClientConfig

USER_AGENT = "polaris-cli/0.1"
GET_RETRIES = 2


class ClientError(Exception):
    """kind: connect / timeout / auth / http / protocol"""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status

    @property
    def exit_code(self) -> int:
        # 3：连接失败、超时、认证失败；4：服务端失败、冲突、不存在、限流
        return 3 if self.kind in ("connect", "timeout", "auth") else 4


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and body.get("detail"):
            return str(body["detail"])
    except ValueError:
        pass
    text = resp.text.strip()
    return text[:200] if text else resp.reason_phrase


def raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = _detail(resp)
    if resp.status_code == 401:
        raise ClientError("auth", f"认证失败：{detail}（检查 POLARIS_ADMIN_TOKEN 或 token_file）", 401)
    if resp.status_code == 429:
        raise ClientError("http", f"请求过于频繁：{detail}", 429)
    raise ClientError("http", f"HTTP {resp.status_code}：{detail}", resp.status_code)


class PolarisClient:
    def __init__(self, cfg: ClientConfig, transport: httpx.AsyncBaseTransport | None = None):
        headers = {"User-Agent": USER_AGENT}
        if cfg.token:
            headers["Authorization"] = f"Bearer {cfg.token}"
        self.base_url = cfg.url
        self._http = httpx.AsyncClient(
            base_url=cfg.url,
            headers=headers,
            timeout=httpx.Timeout(connect=cfg.connect_timeout, read=cfg.read_timeout,
                                  write=cfg.connect_timeout, pool=cfg.connect_timeout),
            follow_redirects=False,
            trust_env=False,      # 本机服务不走系统代理
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def _send(self, method: str, path: str, **kw) -> httpx.Response:
        retries = GET_RETRIES if method == "GET" else 0
        for attempt in range(retries + 1):
            try:
                return await self._http.request(method, path, **kw)
            except httpx.ConnectError as e:
                if attempt < retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise ClientError("connect", f"连不上 {self.base_url}（{e}）")
            except httpx.TimeoutException:
                raise ClientError("timeout", f"请求 {path} 超时")
            except httpx.HTTPError as e:
                raise ClientError("connect", f"请求 {path} 失败：{e}")
        raise AssertionError("unreachable")

    async def request_json(self, method: str, path: str, **kw) -> Any:
        resp = await self._send(method, path, **kw)
        raise_for_status(resp)
        ctype = resp.headers.get("content-type", "")
        if "application/json" not in ctype:
            raise ClientError("protocol", f"{path} 返回的不是 JSON（{ctype or '无 Content-Type'}），服务端可能不支持这个接口")
        try:
            return resp.json()
        except ValueError:
            raise ClientError("protocol", f"{path} 返回的 JSON 无法解析")

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self.request_json("GET", path, params=params)

    async def post(self, path: str, body: dict | None = None, params: dict | None = None) -> Any:
        return await self.request_json("POST", path, json=body, params=params)

    async def put(self, path: str, body: dict) -> Any:
        return await self.request_json("PUT", path, json=body)

    async def stream(self, path: str, body: dict) -> AsyncIterator[bytes]:
        """POST 并逐块产出 SSE 原始字节。不重发：响应丢了也不能确定服务端没执行。"""
        try:
            async with self._http.stream("POST", path, json=body,
                                         headers={"Accept": "text/event-stream"}) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise_for_status(resp)
                ctype = resp.headers.get("content-type", "")
                if "text/event-stream" not in ctype:
                    raise ClientError("protocol", f"{path} 返回的不是事件流（{ctype or '无 Content-Type'}）")
                async for chunk in resp.aiter_raw():
                    yield chunk
        except ClientError:
            raise
        except httpx.ConnectError as e:
            raise ClientError("connect", f"连不上 {self.base_url}（{e}）")
        except httpx.ReadTimeout:
            raise ClientError("timeout", "等待服务端响应超时（长时间没有任何数据），本轮结果未知")
        except httpx.TimeoutException:
            raise ClientError("timeout", f"请求 {path} 超时")
        except httpx.RemoteProtocolError as e:
            raise ClientError("protocol", f"连接被服务端中断：{e}")
        except httpx.HTTPError as e:
            raise ClientError("connect", f"请求 {path} 失败：{e}")
