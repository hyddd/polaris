"""通知：目标配置、主动发送（企业微信 / QQ / 飞书）、频率限制、提醒转发、接口鉴权、AI 工具。不发真实网络请求。"""
import json
import logging
import time
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import config
from src.domains.notify import service, targets as targets_mod, webhook

URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=SECRET-KEY-123"


def _wecom(name="团队群", **kw):
    return {"name": name, "type": "wecom", "url": URL, **kw}


def _wait(cond, timeout=3.0):
    """事件总线和提醒转发在后台线程执行：等它们完成。"""
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


class _WeCom:
    """假的企业微信服务端。"""

    def __init__(self, status=200, body=None, error=None):
        self.requests = []
        self.status, self.error = status, error
        self.body = body if body is not None else {"errcode": 0, "errmsg": "ok"}

    def transport(self):
        def handler(request):
            self.requests.append(request)
            if self.error:
                raise self.error
            return httpx.Response(self.status, json=self.body)
        return httpx.MockTransport(handler)

    def contents(self):
        return [json.loads(r.content)["markdown"]["content"] for r in self.requests]


class _Channel:
    """假的 QQ / 飞书渠道插件。"""

    def __init__(self, name, ok=True, configured=True):
        self.name, self.ok, self.configured, self.sent = name, ok, configured, []

    def is_configured(self):
        return self.configured

    def send_message(self, session_id="", message="", channel=""):
        self.sent.append({"session_id": session_id, "message": message, "channel": channel})
        return self.ok


def _fake_wecom(monkeypatch, wecom=None):
    """接口测试里企业微信走假的服务端。"""
    wecom = wecom or _WeCom()
    real = webhook.send_markdown
    monkeypatch.setattr(service, "send_markdown",
                        lambda url, name, content, transport=None: real(url, name, content, wecom.transport()))
    return wecom


@pytest.fixture
def notify(monkeypatch):
    """设置通知目标和渠道；每个测试重置频率限制。"""
    service.rate_limiter.reset()
    monkeypatch.setitem(config._data, "instance", {"mode": "personal", "name": "张三的 Polaris"})
    channels = []
    monkeypatch.setattr("src.core.channel.loader.get_discovered_channels", lambda: list(channels))

    def setup(webhooks=(), recipients=(), plugins=(), api_token=""):
        monkeypatch.setitem(config._data, "notify",
                            {"webhooks": list(webhooks), "recipients": list(recipients), "api_token": api_token})
        channels[:] = list(plugins)
    yield setup
    service.rate_limiter.reset()


# --- 目标配置 ---

def test_load_targets_validates_and_rejects_duplicates():
    targets, problems = targets_mod.load_targets(
        [_wecom(), _wecom("钉钉", type="dingtalk"), _wecom("明文", url="http://x"), "bad"],
        [{"name": "张三QQ", "channel": "qq:openid-1", "scopes": ["private"]},
         {"name": "项目群", "channel": "feishu-chat:oc_1"},
         {"name": "李四", "channel": "feishu:ou_1"},
         {"name": "无前缀", "channel": "wechat:x"},
         {"name": "空账号", "channel": "qq:"},
         {"name": "团队群", "channel": "qq:dup"},
         {"name": "范围错", "channel": "qq:x", "scopes": ["all"]},
         {"channel": "qq:noname"}])
    assert [(t.name, t.type) for t in targets] == [
        ("团队群", "wecom"), ("张三QQ", "qq"), ("项目群", "feishu-chat"), ("李四", "feishu")]
    assert targets[0].scopes == ["public", "private"] and targets[1].scopes == ["private"]
    assert (targets[2].plugin, targets[2].address) == ("feishu", "oc_1")
    assert len(problems) == 8 and any("重名" in p for p in problems)
    assert all("SECRET-KEY" not in p for p in problems)
    assert "url" not in targets[0].public_dict()


# --- 主动通知 ---

def test_send_to_wecom_qq_feishu(notify):
    qq, feishu = _Channel("qq"), _Channel("feishu")
    notify(webhooks=[_wecom()],
           recipients=[{"name": "张三QQ", "channel": "qq:openid-1"}, {"name": "项目群", "channel": "feishu-chat:oc_1"},
                       {"name": "李四", "channel": "feishu:ou_1"}],
           plugins=[qq, feishu])
    wecom = _WeCom()
    results = service.send_notification(["团队群", "张三QQ", "项目群", "李四"], "发布完成", "v2.3.0 已上线",
                                        source="CI", transport=wecom.transport())
    assert all(r["ok"] for r in results)
    md = wecom.contents()[0]
    assert "📢 **发布完成**" in md and "v2.3.0 已上线" in md and "来自：CI · 张三的 Polaris" in md
    assert qq.sent[0]["channel"] == "qq:openid-1" and qq.sent[0]["message"].startswith("📢 发布完成")
    assert feishu.sent[0] == {"session_id": "oc_1", "message": feishu.sent[0]["message"], "channel": ""}  # 群聊按 chat_id
    assert feishu.sent[1]["channel"] == "feishu:ou_1"                                                   # 私聊按 open_id


def test_send_validation_and_channel_failures(notify):
    notify(webhooks=[_wecom()], recipients=[{"name": "张三QQ", "channel": "qq:o"}, {"name": "李四", "channel": "feishu:ou"}],
           plugins=[_Channel("feishu", ok=False)])
    with pytest.raises(service.NotifyError, match="不存在：王五"):
        service.send_notification(["王五"], "x")
    with pytest.raises(service.NotifyError, match="不能都为空"):
        service.send_notification(["团队群"], "", " ")
    with pytest.raises(service.NotifyError, match="正文最多"):
        service.send_notification(["团队群"], "x", "长" * 4001)
    with pytest.raises(service.NotifyError, match="至少指定"):
        service.send_notification([], "x")
    results = service.send_notification(["张三QQ", "李四"], "x")
    assert results[0] == {"target": "张三QQ", "ok": False, "error": "QQ渠道未启用（channels.qq.enabled）"}
    assert results[1]["ok"] is False and "发送失败" in results[1]["error"]


def test_wecom_rejection_and_network_error(notify, caplog):
    notify(webhooks=[_wecom()])
    caplog.set_level(logging.WARNING, logger="polaris.notify")
    bad = _WeCom(body={"errcode": 93000, "errmsg": "invalid webhook url"})
    assert "errcode=93000" in service.send_notification(["团队群"], "x", transport=bad.transport())[0]["error"]
    down = _WeCom(error=httpx.ConnectError("refused"))
    assert "连不上企业微信" in service.send_notification(["团队群"], "x", transport=down.transport())[0]["error"]
    assert "SECRET-KEY" not in caplog.text


def test_rate_limit_per_target(notify):
    notify(webhooks=[_wecom(), _wecom("另一个群")])
    wecom = _WeCom()
    for _ in range(service.RATE_LIMIT):
        assert service.send_notification(["团队群"], "x", transport=wecom.transport())[0]["ok"]
    over = service.send_notification(["团队群", "另一个群"], "x", transport=wecom.transport())
    assert over[0]["ok"] is False and "频率限制" in over[0]["error"]
    assert over[1]["ok"] is True                                   # 按目标分别计数


def test_wecom_content_truncated_to_limit():
    text = webhook.truncate_bytes("很长" * 3000)
    assert len(text.encode("utf-8")) <= webhook.WECOM_MARKDOWN_LIMIT and text.endswith("（已截断）")


def test_httpx_request_log_hides_webhook_key(caplog):
    caplog.set_level(logging.INFO, logger="httpx")
    logging.getLogger("httpx").info('HTTP Request: POST %s "HTTP/1.1 200 OK"', URL)
    assert "SECRET-KEY" not in caplog.text and "key=***" in caplog.text


# --- 提醒转发：所有类型的目标按 scopes 转发 ---

def test_forward_reminder_to_all_matching_targets(notify):
    qq = _Channel("qq")
    notify(webhooks=[_wecom(scopes=["public"])],
           recipients=[{"name": "张三QQ", "channel": "qq:o", "scopes": ["private"]},
                       {"name": "全部QQ", "channel": "qq:all"}],
           plugins=[qq])
    wecom = _WeCom()
    reminder = {"title": "周会", "description": "带上周报", "trigger_time": "2026-11-18T15:00:00", "scope": "public"}
    assert service.forward_reminder(reminder, wecom.transport(), background=False) == ["团队群", "全部QQ"]
    assert "⏰ **提醒：周会**" in wecom.contents()[0] and '<font color="info">公共</font>' in wecom.contents()[0]
    assert [m["channel"] for m in qq.sent] == ["qq:all"] and "时间：2026-11-18 15:00" in qq.sent[0]["message"]
    assert service.forward_reminder({**reminder, "scope": "private"}, wecom.transport(), background=False) == ["张三QQ", "全部QQ"]


def test_reminder_trigger_reaches_targets(tmp_path, monkeypatch, notify, session_mgr):
    """提醒到点 → reminder:triggered（带范围、说明、时间）→ 转发；创建时已过期的一次性提醒同样转发。"""
    from src.domains.reminder.domain import ReminderDomain
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.store import ReminderStore

    class _Scheduler:
        def add_date_job(self, **kw): pass
        def add_cron_job(self, **kw): pass
        def remove_job(self, job_id): return True
    monkeypatch.setattr("src.domains.scheduler.get_scheduler_domain", lambda: _Scheduler())
    monkeypatch.setitem(config._data, "remote", {"url": ""})
    qq = _Channel("qq")
    notify(recipients=[{"name": "我的QQ", "channel": "qq:me", "scopes": ["private"]}], plugins=[qq])

    store = ReminderStore(str(tmp_path / "rem.json"))
    domain = ReminderDomain(store, ReminderHandler([], store=store))
    r = domain.create(title="交周报", description="周五前", trigger_time=datetime.now() + timedelta(hours=1))
    domain.trigger(r.id)
    assert _wait(lambda: len(qq.sent) == 1)
    assert "交周报" in qq.sent[0]["message"] and "周五前" in qq.sent[0]["message"] and "私人" in qq.sent[0]["message"]
    domain.create(title="已过期", trigger_time=datetime.now() - timedelta(minutes=1))
    assert _wait(lambda: len(qq.sent) == 2) and "已过期" in qq.sent[1]["message"]


def test_forward_failure_never_breaks_reminder(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(service, "forward_reminder", boom)
    service._on_reminder_triggered(title="x", scope="private")   # 不抛异常


# --- 接口与鉴权 ---

def _client():
    from src.server.middleware import admin_auth
    from src.server.routes import notify as notify_routes
    app = FastAPI()
    app.middleware("http")(admin_auth)
    app.include_router(notify_routes.router)
    return TestClient(app)


def test_api_open_when_token_empty(notify, monkeypatch):
    notify(webhooks=[_wecom()])
    _fake_wecom(monkeypatch)
    c = _client()
    assert c.get("/api/notify/targets").json()["targets"][0] == {
        "name": "团队群", "type": "wecom", "scopes": ["public", "private"], "available": True}
    r = c.post("/api/notify/send", json={"targets": ["团队群"], "title": "构建失败"})
    assert r.status_code == 200 and r.json()["results"] == [{"target": "团队群", "ok": True}]
    assert c.post("/api/notify/send", json={"targets": ["王五"], "title": "x"}).status_code == 400


def test_api_token_required_when_set(notify, monkeypatch):
    notify(webhooks=[_wecom()], api_token="t0ken")
    _fake_wecom(monkeypatch)
    c = _client()
    assert c.get("/api/notify/targets").status_code == 401
    assert c.get("/api/notify/targets", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/notify/targets", headers={"Authorization": "Bearer t0ken"}).status_code == 200


def test_api_token_and_admin_token_interplay(notify, monkeypatch):
    """配置了 notify.api_token：通知接口只认它（CI 不需要 admin_token）；没配置：通知接口和其他接口一样受 admin_token 约束。"""
    monkeypatch.setitem(config._data, "server", {**config._data.get("server", {}), "admin_token": "admin"})
    notify(webhooks=[_wecom()], api_token="t0ken")
    c = _client()
    assert c.get("/api/notify/targets", headers={"Authorization": "Bearer t0ken"}).status_code == 200
    notify(webhooks=[_wecom()], api_token="")
    assert c.get("/api/notify/targets").status_code == 401
    assert c.get("/api/notify/targets", headers={"Authorization": "Bearer admin"}).status_code == 200


def test_api_429_when_all_targets_rate_limited(notify, monkeypatch):
    notify(webhooks=[_wecom()])
    monkeypatch.setattr(service, "RATE_LIMIT", 1)
    service.rate_limiter.limit = 1
    _fake_wecom(monkeypatch)
    c = _client()
    assert c.post("/api/notify/send", json={"targets": ["团队群"], "content": "a"}).status_code == 200
    assert c.post("/api/notify/send", json={"targets": ["团队群"], "content": "b"}).status_code == 429
    service.rate_limiter.limit = service.RATE_LIMIT


# --- AI 工具 ---

def test_ai_tool_list_and_send(notify):
    from src.tools.notify.tool import NotifyTool
    qq = _Channel("qq")
    notify(recipients=[{"name": "张三QQ", "channel": "qq:o"}, {"name": "李四", "channel": "feishu:ou"}], plugins=[qq])
    tool = NotifyTool()
    listing = tool._run(action="list")
    assert "张三QQ（qq，可用）" in listing and "李四（feishu，不可用" in listing
    out = tool._run(action="send", targets=["张三QQ", "李四"], title="今日待办", content="- 交周报")
    assert "张三QQ：已发送" in out and "李四：失败" in out
    assert "来自：AI" in qq.sent[0]["message"]
    assert tool._run(action="send", targets=["王五"], content="x").startswith("发送失败：通知目标不存在")


# --- 飞书渠道：发送失败要如实返回 ---

def test_feishu_send_reports_api_failure():
    from src.channels.feishu.client import FeishuChannel, PolarisFeishuBot

    class _Resp:
        def __init__(self, ok): self.ok, self.code, self.msg = ok, 230002, "bot not in chat"
        def success(self): return self.ok

    bot = PolarisFeishuBot.__new__(PolarisFeishuBot)
    responses = [_Resp(False), _Resp(True)]
    bot.client = type("C", (), {"im": type("I", (), {"v1": type("V", (), {
        "message": type("M", (), {"create": staticmethod(lambda req: responses.pop(0))})()})()})()})()
    ch = FeishuChannel.__new__(FeishuChannel)
    ch._bot = bot
    assert ch.send_message(session_id="oc_1", message="hi", channel="") is False
    assert ch.send_message(session_id="", message="hi", channel="feishu:ou_1") is True
