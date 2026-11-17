"""待办的公共存储和公私组合存储。

- PublicTodoStore：team 服务用，直接读写 MySQL；
- RemoteTodoStore：personal 服务用，调 team 服务的 /api/data/todos 接口；
- ScopedTodoStore：组合存储，对外和 TodoStore 接口一致，TodoDomain 不用关心数据在哪：
  创建按 data["scope"] 分流，列表/搜索两边合并（公共读不到时只显示私人并记下原因），
  按 ID 修改/删除先找私人再找公共。team 模式私人一侧是 NoPrivate。
"""
import logging

from src.core.db import PUBLIC, PRIVATE
from src.core.db.public_store import (PrivateOnly, PublicStoreBase, MergedReadMixin, dump_list, load_list,
                                      date_str, now)
from src.core.db.remote import RemoteError, get_remote
from .models import TodoItem
from .store import TodoStore

logger = logging.getLogger("polaris.todos.public")

_UPDATABLE = {"title", "priority", "status", "due", "tags"}


class RemoteTodoStore:
    """personal → team：公共待办通过 HTTP 读写。team 接口返回的就是公共数据。"""

    def __init__(self, client_getter=get_remote):
        self._client_getter = client_getter

    def _c(self):
        c = self._client_getter()
        if c is None:
            raise RemoteError("没有连接团队服务")
        return c

    def _item(self, d: dict) -> TodoItem:
        return TodoItem.from_dict({**d, "scope": PUBLIC})

    def _all(self) -> list[TodoItem]:
        return [self._item(d) for d in self._c().get("/api/data/todos").get("items", [])]

    def list_todos(self, status: str | None = None) -> list[TodoItem]:
        items = self._all()
        if status is None or status == "active":
            return [t for t in items if t.status in ("pending", "in_progress")]
        if status == "all":
            return items
        return [t for t in items if t.status == status]

    def get_todo(self, todo_id: str) -> TodoItem | None:
        return next((t for t in self._all() if t.id == todo_id), None)

    def search(self, keyword: str) -> list[TodoItem]:
        kw = keyword.lower()
        return [t for t in self._all() if kw in t.title.lower() or kw in " ".join(t.tags).lower()]

    def create_todo(self, data: dict) -> TodoItem:
        body = {k: data.get(k) for k in ("title", "priority", "due")}
        return self._item(self._c().post("/api/data/todos", {"data": {**body, "scope": PUBLIC}})["item"])

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
        try:
            r = self._c().put(f"/api/data/todos/{todo_id}", {"data": updates})
        except RemoteError as e:
            if e.status == 404:
                return None
            raise
        return self._item(r["item"]) if r.get("item") else self.get_todo(todo_id)

    def mark_done(self, todo_id: str) -> TodoItem | None:
        return self.update_todo(todo_id, {"status": "done"})

    def delete_todo(self, todo_id: str) -> bool:
        try:
            self._c().delete(f"/api/data/todos/{todo_id}")
            return True
        except RemoteError as e:
            if e.status == 404:
                return False
            raise


class PublicTodoStore(PublicStoreBase):

    def _row(self, r: dict) -> TodoItem:
        return TodoItem(id=r["id"], title=r["title"], priority=r["priority"], status=r["status"],
                        due=date_str(r["due_date"]), tags=load_list(r["tags"]), scope=PUBLIC)

    def list_todos(self, status: str | None = None) -> list[TodoItem]:
        db = self.db()
        sql = f"SELECT * FROM {db.t('todos')}"
        args: tuple = ()
        if status is None or status == "active":
            sql += " WHERE status IN ('pending','in_progress')"
        elif status != "all":
            sql += " WHERE status=%s"
            args = (status,)
        sql += " ORDER BY created_at"
        return [self._row(r) for r in db.fetchall(sql, args)]

    def get_todo(self, todo_id: str) -> TodoItem | None:
        db = self.db()
        r = db.fetchone(f"SELECT * FROM {db.t('todos')} WHERE id=%s", (todo_id,))
        return self._row(r) if r else None

    def search(self, keyword: str) -> list[TodoItem]:
        db = self.db()
        like = f"%{keyword}%"
        rows = db.fetchall(f"SELECT * FROM {db.t('todos')} WHERE title LIKE %s OR tags LIKE %s "
                           f"ORDER BY created_at", (like, like))
        return [self._row(r) for r in rows]

    def create_todo(self, data: dict) -> TodoItem:
        db = self.db()
        todo = TodoItem.from_dict({**data, "scope": PUBLIC})
        ts = now()
        db.execute(f"INSERT INTO {db.t('todos')} (id, title, priority, status, due_date, tags, created_at, updated_at) "
                   f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                   (todo.id, todo.title, todo.priority, todo.status, todo.due or None, dump_list(todo.tags), ts, ts))
        return todo

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
        fields = {k: v for k, v in updates.items() if k in _UPDATABLE}
        ignored = set(updates) - _UPDATABLE
        if ignored:
            logger.info(f"公共待办 {todo_id} 忽略不支持修改的字段：{sorted(ignored)}")
        db = self.db()
        if fields:
            column = {"due": "due_date"}
            sets, args = [], []
            for k, v in fields.items():
                sets.append(f"{column.get(k, k)}=%s")
                if k == "due":
                    v = v or None
                elif k == "tags":
                    v = dump_list(v)
                args.append(v)
            sets.append("updated_at=%s")
            args += [now(), todo_id]
            db.execute(f"UPDATE {db.t('todos')} SET {', '.join(sets)} WHERE id=%s", args)
        return self.get_todo(todo_id)

    def mark_done(self, todo_id: str) -> TodoItem | None:
        return self.update_todo(todo_id, {"status": "done"})

    def delete_todo(self, todo_id: str) -> bool:
        db = self.db()
        return db.execute(f"DELETE FROM {db.t('todos')} WHERE id=%s", (todo_id,)) > 0


class ScopedTodoStore(MergedReadMixin):
    def __init__(self, private: TodoStore, public: PublicTodoStore | None):
        self._private = PrivateOnly(private)
        self._public = public

    def list_todos(self, status: str | None = None) -> list[TodoItem]:
        return self._private.list_todos(status) + self._public_read(lambda: self._public.list_todos(status), [])

    def get_todo(self, todo_id: str) -> TodoItem | None:
        return self._private.get_todo(todo_id) or self._public_read(lambda: self._public.get_todo(todo_id), None)

    def search(self, keyword: str) -> list[TodoItem]:
        return self._private.search(keyword) + self._public_read(lambda: self._public.search(keyword), [])

    def _owner(self, todo_id: str):
        if self._private.get_todo(todo_id):
            return self._private
        if self._public is not None and self._public.get_todo(todo_id):
            return self._public
        return None

    def create_todo(self, data: dict) -> TodoItem:
        if data.get("scope") == PUBLIC:
            if self._public is None:
                raise RuntimeError("公共库未启用，不能创建公共待办")
            return self._public.create_todo(data)
        return self._private.create_todo({**data, "scope": PRIVATE})

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
        owner = self._owner(todo_id)
        return owner.update_todo(todo_id, updates) if owner else None

    def mark_done(self, todo_id: str) -> TodoItem | None:
        owner = self._owner(todo_id)
        return owner.mark_done(todo_id) if owner else None

    def delete_todo(self, todo_id: str) -> bool:
        owner = self._owner(todo_id)
        return owner.delete_todo(todo_id) if owner else False

    def cleanup(self, days: int = 30) -> int:
        # 只清理本机私有数据；公共数据是大家的，不由某个人的实例按自己的配置删除
        return self._private.cleanup(days)
