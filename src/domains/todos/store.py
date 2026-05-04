"""TodoStore — 待办事项 JSON 文件持久化。"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from src.storage.atomic import _atomic_write
from .models import TodoItem

logger = logging.getLogger("polaris.todos.store")


class TodoStore:
    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._lock = threading.Lock()
        self._todos: list[TodoItem] = []
        self._load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self):
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._todos = [TodoItem.from_dict(item) for item in data]
            else:
                self._todos = []
            logger.info(f"已加载 {len(self._todos)} 条待办")

    def _save(self):
        data = [t.to_dict() for t in self._todos]
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path, content)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_todos(self, status: str | None = None) -> list[TodoItem]:
        """列出待办。status=None 或 'active' 返回 pending+in_progress。"""
        if status is None or status == "active":
            return [t for t in self._todos if t.status in ("pending", "in_progress")]
        if status == "all":
            return list(self._todos)
        return [t for t in self._todos if t.status == status]

    def get_todo(self, todo_id: str) -> TodoItem | None:
        for t in self._todos:
            if t.id == todo_id:
                return t
        return None

    def search(self, keyword: str) -> list[TodoItem]:
        kw = keyword.lower()
        return [
            t for t in self._todos
            if kw in t.title.lower() or kw in " ".join(t.tags).lower()
        ]

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def create_todo(self, data: dict) -> TodoItem:
        todo = TodoItem.from_dict(data)
        with self._lock:
            self._todos.append(todo)
            self._save()
        return todo

    def update_todo(self, todo_id: str, updates: dict) -> TodoItem | None:
        with self._lock:
            todo = self.get_todo(todo_id)
            if not todo:
                return None
            for k, v in updates.items():
                if hasattr(todo, k):
                    setattr(todo, k, v)
            self._save()
        return todo

    def mark_done(self, todo_id: str) -> TodoItem | None:
        with self._lock:
            todo = self.get_todo(todo_id)
            if not todo:
                return None
            todo.status = "done"
            self._save()
        return todo

    def delete_todo(self, todo_id: str) -> bool:
        with self._lock:
            for i, t in enumerate(self._todos):
                if t.id == todo_id:
                    self._todos.pop(i)
                    self._save()
                    return True
        return False

    # ------------------------------------------------------------------
    # 维护
    # ------------------------------------------------------------------

    def cleanup(self, days: int = 30) -> int:
        """清理状态为 done 且在指定天数之前创建的待办。"""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        with self._lock:
            before = len(self._todos)
            self._todos = [
                t for t in self._todos
                if not (t.status == "done" and t.due and t.due < cutoff_str)
            ]
            removed = before - len(self._todos)
            if removed:
                self._save()
                logger.info(f"已清理 {removed} 条过期待办")
        return removed
