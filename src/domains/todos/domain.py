"""TodoDomain — 待办管理核心服务。"""

import logging
import uuid

from src.core.infra import event_bus
from src.core.tools import find_by_id_or_title
from .models import TodoItem
from .store import TodoStore

logger = logging.getLogger("polaris.todos")


class TodoDomain:
    def __init__(self, store: TodoStore):
        self._store = store

    @property
    def public_error(self) -> str | None:
        """最近一次读公共库失败的原因（列表里只剩私有数据时用来提示）。"""
        return getattr(self._store, "public_error", None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_todos(self, status: str = "active") -> list[TodoItem]:
        return self._store.list_todos(status)

    def get_todo(self, todo_id: str) -> TodoItem | None:
        return self._store.get_todo(todo_id)

    def search(self, keyword: str) -> list[TodoItem]:
        return self._store.search(keyword)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def create_todo(self, title: str, priority: str = "medium",
                    due: str = "", channel: str = "admin",
                    session_id: str = "", scope: str | None = None) -> TodoItem:
        """scope：public 存公共库、private 存本机；不传用默认（visibility.default_scope）。"""
        from src.core.db import resolve_scope
        scope = resolve_scope(scope)
        todo_id = f"todo-{uuid.uuid4().hex[:8]}"
        data = {
            "id": todo_id,
            "title": title,
            "priority": priority,
            "status": "pending",
            "due": due,
            "tags": [],
            "scope": scope,
        }
        todo = self._store.create_todo(data)
        # personal 存公共待办时 ID 由 team 服务分配，以存储返回的为准
        event_bus.publish("todos:todo_created",
                          todo_id=todo.id, title=title, priority=priority, scope=scope)
        logger.info(f"已创建{scope}待办: {todo.id} ({title})")
        return todo

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
        if "scope" in updates:
            from src.core.db import ScopeError
            raise ScopeError("不支持修改公共/私人范围。如需改为另一种范围，请按新范围新建一条，再删除原来的")
        todo = self._store.update_todo(todo_id, updates)
        if todo:
            event_bus.publish("todos:todo_updated",
                              todo_id=todo.id, title=todo.title,
                              status=todo.status)
            logger.info(f"已更新待办: {todo.id}")
        return todo

    def mark_done(self, todo_id: str) -> TodoItem | None:
        todo = self._store.mark_done(todo_id)
        if todo:
            event_bus.publish("todos:todo_updated",
                              todo_id=todo.id, title=todo.title,
                              status=todo.status)
            logger.info(f"已标记完成: {todo.id} ({todo.title})")
        return todo

    def delete_todo(self, todo_id: str) -> bool:
        todo = self._store.get_todo(todo_id)
        title = todo.title if todo else ""
        deleted = self._store.delete_todo(todo_id)
        if deleted:
            event_bus.publish("todos:todo_deleted", todo_id=todo_id)
            logger.info(f"已删除待办: {todo_id} ({title})")
        return deleted

    # ------------------------------------------------------------------
    # 维护
    # ------------------------------------------------------------------

    def cleanup(self, days: int = 30) -> int:
        removed = self._store.cleanup(days)
        if removed:
            logger.info(f"待办清理完成，移除 {removed} 条")
        return removed


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: TodoDomain | None = None


def get_todo_domain() -> TodoDomain:
    return _domain


def set_todo_domain(domain: TodoDomain):
    global _domain
    _domain = domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(**kwargs):
    from src.core.config import config
    from src.core.db import is_team, public_enabled, instance_info
    from src.core.db.public_store import NoPrivate
    from .public_store import PublicTodoStore, RemoteTodoStore, ScopedTodoStore
    if is_team():
        # 团队服务：没有私人数据，公共数据直接读写 MySQL
        store = ScopedTodoStore(NoPrivate(), PublicTodoStore() if public_enabled() else None)
    else:
        # 个人服务：私人存本机文件，公共数据通过 HTTP 调团队服务
        path = str(config.resolve_path(config.get("storage.todos_file", "data/todos.json")))
        store = ScopedTodoStore(TodoStore(path), RemoteTodoStore() if public_enabled() else None)
    domain = TodoDomain(store)
    set_todo_domain(domain)
    logger.info(f"待办域已启动（{instance_info()['mode_label']}，公共数据{'可用' if public_enabled() else '未启用'}）")


def _on_cleanup_now(**kwargs):
    domain = get_todo_domain()
    if domain:
        domain.cleanup()


def _on_cleanup_cron(**kwargs):
    domain = get_todo_domain()
    if domain:
        domain.cleanup()


event_bus.subscribe("app:startup", _on_startup)
event_bus.subscribe("cleanup:now", _on_cleanup_now)
event_bus.subscribe("cleanup:cron", _on_cleanup_cron)
