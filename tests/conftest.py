import os
import tempfile
import pytest
from pathlib import Path

os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["LLM_MODEL"] = "gpt-4o"
# 数据路径在模块 import 时按 POLARIS_HOME 算出；不覆盖的话测试会往项目正式的 data/ 里写会话文件
os.environ["POLARIS_HOME"] = tempfile.mkdtemp(prefix="polaris-test-")


@pytest.fixture
def session_mgr(tmp_path, monkeypatch):
    """每个测试一个全新的 SessionManager，会话文件落在 tmp_path，并替换全局单例。"""
    import src.session.manager as manager_mod
    import src.core.infra.lock as lock_mod

    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(manager_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(manager_mod, "ACTIVE_FILE", sessions_dir / "active.json")
    monkeypatch.setattr(manager_mod, "DATA_DIR", tmp_path)
    lock_mod._message_locks.clear()
    mgr = manager_mod.SessionManager()
    monkeypatch.setattr(manager_mod, "_session_manager", mgr)
    return mgr


@pytest.fixture
def sample_calendar_data():
    return [
        {
            "date": "2026-05-03",
            "events": [
                {"id": "evt-1", "time": "09:00", "title": "晨会", "attendees": ["Alice", "Bob"], "duration": 30},
                {"id": "evt-2", "time": "15:00", "title": "产品方案评审", "attendees": ["张三", "李四"], "duration": 60},
            ]
        }
    ]


@pytest.fixture
def sample_todo_data():
    return [
        {"id": "todo-1", "title": "完成权限设计文档", "priority": "high", "status": "pending", "due": "2026-05-02", "tags": ["产品"]},
        {"id": "todo-2", "title": "Code Review PR #42", "priority": "medium", "status": "in_progress", "due": "2026-05-01", "tags": ["开发"]},
        {"id": "todo-3", "title": "更新 README", "priority": "low", "status": "done", "due": "2026-04-28", "tags": ["文档"]},
    ]


@pytest.fixture
def sample_note_content():
    return """---
title: "PRD v2 讨论"
tags: ["产品", "评审"]
date: "2026-04-15"
---

讨论了用户权限方案。
决定采用 RBAC 模型。
待确认：多租户隔离方案。
"""


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory with seed files."""
    import json

    notes_dir = tmp_path / "notes"
    archive_dir = notes_dir / "archive"
    notes_dir.mkdir(parents=True)
    archive_dir.mkdir()

    (notes_dir / "prd-v2-discussion.md").write_text("""---
title: "PRD v2 讨论"
tags: ["产品", "评审"]
date: "2026-04-15"
---

讨论了用户权限方案。
决定采用 RBAC 模型。
待确认：多租户隔离方案。
""")

    (tmp_path / "calendar.json").write_text(json.dumps([
        {"date": "2026-05-03", "events": [
            {"id": "evt-1", "time": "09:00", "title": "晨会", "attendees": ["Alice"], "duration": 30},
            {"id": "evt-2", "time": "15:00", "title": "产品评审", "attendees": ["张三"], "duration": 60},
        ]}
    ], ensure_ascii=False))

    (tmp_path / "todos.json").write_text(json.dumps([
        {"id": "todo-1", "title": "完成权限设计文档", "priority": "high", "status": "pending", "due": "2026-05-02", "tags": ["产品"]},
    ], ensure_ascii=False))

    (tmp_path / "user_profile.json").write_text(json.dumps({"name": "TestUser", "preferred_working_hours": "9:00-18:00"}, ensure_ascii=False))

    return tmp_path
