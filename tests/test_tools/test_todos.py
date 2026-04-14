import json
from src.tools.todos import TodoTool


def test_todo_list_all(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="list", status="all")
    assert "完成权限设计文档" in result


def test_todo_list_active(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="list", status="active")
    assert "完成权限设计文档" in result


def test_todo_list_defaults_to_active(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="list")
    assert "完成权限设计文档" in result


def test_todo_search(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="search", keyword="权限")
    assert "完成权限设计文档" in result


def test_todo_create(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="create", title="新待办", priority="high", due="2026-05-10")
    assert "新待办" in result
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert any(t["title"] == "新待办" for t in data)


def test_todo_mark_done(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run(action="done", todo_id="todo-1")
    assert "已完成" in result


def test_todo_delete(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    tool._run(action="delete", todo_id="todo-1")
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert not any(t["id"] == "todo-1" for t in data)
