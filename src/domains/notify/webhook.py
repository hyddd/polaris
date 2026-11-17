"""企业微信群机器人 webhook：消息格式与发送。

- 日志里只出现目标名称，不出现 url（url 里的 key 相当于密码）；
- httpx 在 INFO 级别会记录完整请求地址，这里给 httpx 的日志加过滤，把 key 遮掉。
"""
import logging
import re

import httpx

logger = logging.getLogger("polaris.notify")

WECOM_MARKDOWN_LIMIT = 4096        # 企业微信 markdown 内容上限（字节）
TIMEOUT = 5.0


class _RedactWebhookKey(logging.Filter):
    _pattern = re.compile(r"([?&]key=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.msg, record.args = record.getMessage(), None
        if isinstance(record.msg, str) and "key=" in record.msg:
            record.msg = self._pattern.sub(r"\1***", record.msg)
        return True


logging.getLogger("httpx").addFilter(_RedactWebhookKey())


def truncate_bytes(text: str, limit: int = WECOM_MARKDOWN_LIMIT) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    suffix = "\n…（已截断）"
    return encoded[:limit - len(suffix.encode("utf-8"))].decode("utf-8", "ignore") + suffix


def send_markdown(url: str, name: str, content: str, transport: httpx.BaseTransport | None = None) -> tuple[bool, str]:
    """发送一条 markdown 消息，返回 (是否成功, 失败原因)。"""
    payload = {"msgtype": "markdown", "markdown": {"content": truncate_bytes(content)}}
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport) as client:
            resp = client.post(url, json=payload)
    except httpx.HTTPError as e:
        logger.warning(f"企业微信发送失败（{name}）：{type(e).__name__}")
        return False, f"连不上企业微信（{type(e).__name__}）"
    try:
        result = resp.json()
    except ValueError:
        result = {}
    if resp.status_code != 200 or result.get("errcode") != 0:
        reason = f"企业微信拒绝：HTTP {resp.status_code}，errcode={result.get('errcode')}，{result.get('errmsg', '')}"
        logger.warning(f"{reason}（{name}）")
        return False, reason
    return True, ""
