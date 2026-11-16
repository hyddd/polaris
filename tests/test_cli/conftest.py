"""终端客户端测试的公共夹具。

live_server：在测试进程里起一个真实的 uvicorn，挂真实的聊天/会话/数据/提醒/状态路由，
只把 agent 图换成脚本（tests/test_message/_fakes.Script），客户端走真实的 HTTP + SSE。
"""
import socket
import threading
import time
from dataclasses import dataclass

import pytest
import uvicorn
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def _isolate_cli(tmp_path, monkeypatch):
    """客户端本地状态放到临时目录；清掉可能影响结果的环境变量；禁止误用真实 LLM。"""
    monkeypatch.setenv("POLARIS_CLI_HOME", str(tmp_path / "cli-home"))
    for var in ("POLARIS_URL", "POLARIS_ADMIN_TOKEN", "POLARIS_PROFILE", "POLARIS_CLI_CONFIG", "NO_COLOR"):
        monkeypatch.delenv(var, raising=False)

    def _no_llm():
        raise AssertionError("测试误用了真实 LLM（会发网络请求）")
    monkeypatch.setattr("src.agent.executor._get_llm", _no_llm)


@dataclass
class LiveServer:
    url: str
    graph_holder: dict
    auth: dict

    def use(self, graph):
        self.graph_holder["graph"] = graph
        return graph


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(session_mgr, tmp_path, monkeypatch):
    import src.message.router as router_mod
    import src.server.routes.chat as chat_routes
    import src.server.routes.data as data_routes
    import src.server.routes.reminders as reminder_routes
    from src.server.routes import sessions as session_routes
    from src.server.routes.status import router as status_router
    from src.domains.calendar.domain import CalendarDomain
    from src.domains.calendar.store import CalendarStore
    from src.domains.reminder.domain import ReminderDomain
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.store import ReminderStore
    from src.domains.todos.domain import TodoDomain
    from src.domains.todos.store import TodoStore
    from tests.test_message._fakes import Script
    from langchain_core.messages import AIMessage

    holder = {"graph": Script([AIMessage(content="默认回复")] * 20).build()}
    monkeypatch.setattr(chat_routes, "get_agent", lambda: holder["graph"])
    monkeypatch.setattr(router_mod, "get_agent", lambda: holder["graph"])

    todos = TodoDomain(TodoStore(str(tmp_path / "todos.json")))
    calendar = CalendarDomain(CalendarStore(str(tmp_path / "calendar.json")))
    store = ReminderStore(str(tmp_path / "reminders.json"))
    reminders = ReminderDomain(store, ReminderHandler([], store=store))
    monkeypatch.setattr(data_routes, "_require_todo_domain", lambda: todos)
    monkeypatch.setattr(data_routes, "_require_calendar_domain", lambda: calendar)
    monkeypatch.setattr(reminder_routes, "_require_reminder_domain", lambda: reminders)

    auth = {"token": ""}

    app = FastAPI()

    @app.middleware("http")
    async def _auth(request, call_next):
        # 与 src/server/middleware/auth.py 同样的规则，token 由测试控制
        from fastapi.responses import JSONResponse
        if request.url.path.startswith("/api/") and auth["token"]:
            if request.headers.get("authorization", "") != f"Bearer {auth['token']}":
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid admin token"})
        return await call_next(request)

    for r in (chat_routes.router, session_routes.router, data_routes.router, reminder_routes.router, status_router):
        app.include_router(r)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("测试服务没能启动")
        time.sleep(0.02)
    ls = LiveServer(url=f"http://127.0.0.1:{port}", graph_holder=holder, auth=auth)
    ls.todos, ls.calendar, ls.reminders = todos, calendar, reminders
    yield ls
    server.should_exit = True
    t.join(timeout=10)
