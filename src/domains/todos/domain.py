"""TodoDomain — 待办管理核心服务。"""

import logging
import uuid

from src.core.events import event_bus
from src.tools.entity_utils import find_by_id_or_title
from .models import TodoItem
from .store import TodoStore

logger = logging.getLogger("polaris.todos")


class TodoDomain:
    def __init__(self, store: TodoStore):
        self._store = store

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
                    session_id: str = "") -> TodoItem:
        todo_id = f"todo-{uuid.uuid4().hex[:8]}"
        data = {
            "id": todo_id,
            "title": title,
            "priority": priority,
            "status": "pending",
            "due": due,
            "tags": [],
        }
        todo = self._store.create_todo(data)
        event_bus.publish("todos:todo_created",
                          todo_id=todo_id, title=title, priority=priority)
        logger.info(f"已创建待办: {todo_id} ({title})")
        return todo

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
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
    path = str(config.resolve_path(
        config.get("storage.todos_file", "data/todos.json")))
    store = TodoStore(path)
    domain = TodoDomain(store)
    set_todo_domain(domain)
    logger.info("待办域已启动")


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
