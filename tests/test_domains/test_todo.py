"""TodoDomain 单元测试。"""

import re

import pytest

from src.domains.todos.store import TodoStore
from src.domains.todos.domain import TodoDomain


@pytest.fixture
def domain(tmp_path):
    store = TodoStore(str(tmp_path / "todos.json"))
    return TodoDomain(store)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


def test_create_todo(domain):
    todo = domain.create_todo("买菜", priority="high", due="2026-05-10")
    assert todo.title == "买菜"
    assert todo.priority == "high"
    assert todo.status == "pending"
    assert todo.due == "2026-05-10"
    assert re.match(r"^todo-[0-9a-f]{8}$", todo.id)


def test_list_active(domain):
    domain.create_todo("待办A")
    t2 = domain.create_todo("待办B")
    domain.mark_done(t2.id)
    active = domain.list_todos("active")
    assert len(active) == 1
    assert active[0].title == "待办A"


def test_list_all(domain):
    domain.create_todo("待办A")
    t2 = domain.create_todo("待办B")
    domain.mark_done(t2.id)
    all_todos = domain.list_todos("all")
    assert len(all_todos) == 2


def test_search(domain):
    domain.create_todo("买菜做饭")
    domain.create_todo("写代码")
    domain.create_todo("买水果")
    results = domain.search("买")
    assert len(results) == 2
    titles = [t.title for t in results]
    assert "买菜做饭" in titles
    assert "买水果" in titles


def test_update_todo(domain):
    todo = domain.create_todo("原标题", priority="low")
    updated = domain.update_todo(todo.id, {"title": "新标题", "priority": "high"})
    assert updated is not None
    assert updated.title == "新标题"
    assert updated.priority == "high"


def test_mark_done(domain):
    todo = domain.create_todo("待完成")
    done = domain.mark_done(todo.id)
    assert done is not None
    assert done.status == "done"


def test_delete_todo(domain):
    todo = domain.create_todo("待删除")
    assert domain.delete_todo(todo.id) is True
    assert domain.get_todo(todo.id) is None


def test_cleanup(domain):
    # 旧任务：已完成 + 过期 due -> 应被清理
    old = domain.create_todo("旧任务", due="2020-01-01")
    domain.mark_done(old.id)
    # 新任务：已完成 + 近期 due -> 不应被清理
    recent = domain.create_todo("新任务", due="2026-12-31")
    domain.mark_done(recent.id)
    # 未完成的任务 -> 不应被清理
    domain.create_todo("进行中", due="2020-01-01")

    removed = domain.cleanup(days=7)
    assert removed == 1
    assert domain.get_todo(old.id) is None
    assert domain.get_todo(recent.id) is not None
