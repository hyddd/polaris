import os
import pytest
from pathlib import Path

os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["LLM_MODEL"] = "gpt-4o"


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
