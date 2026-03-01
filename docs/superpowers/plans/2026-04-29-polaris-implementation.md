# Polaris Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal efficiency AI Agent with 5 capabilities (daily planning, meeting prep, knowledge search, quick capture, manage) using LangGraph state machine, accessible via Chainlit Web UI and Feishu Bot.

**Architecture:** Three-layer design — entry layer (Chainlit + Feishu Bot) sends messages via unified protocol to the LangGraph agent core (Router → 5 skill subgraphs → Summarize), which invokes 4 tools (GoogleCalendar, Note, Todo, RAGSearch) through a shared ToolRegistry. Memory persists across turns via ConversationBufferWindowMemory.

**Tech Stack:** Python 3.11+, LangGraph, LangChain, Chainlit, ChromaDB, Google Calendar API v3, venv + pyproject.toml + pip, pytest

---

## File Structure

```
AgentPlan/
├── pyproject.toml
├── .env.example
├── .gitignore
├── data/
│   ├── calendar.json          # Seed calendar events
│   ├── todos.json             # Seed todo items
│   ├── user_profile.json      # User preferences
│   └── notes/
│       ├── sample-meeting.md  # Sample note for RAG testing
│       └── archive/           # Archived notes
├── src/
│   ├── __init__.py
│   ├── config.py              # Env/config loading
│   ├── state.py               # AgentState TypedDict
│   ├── protocol.py            # Message protocol types
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py        # ToolRegistry
│   │   ├── calendar.py        # GoogleCalendarTool
│   │   ├── notes.py           # NoteTool
│   │   ├── todos.py           # TodoTool
│   │   └── rag.py             # RAGSearchTool
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py           # Graph assembly
│   │   ├── router.py          # Router node
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── planning.py    # Daily Planning
│   │   │   ├── prep.py        # Meeting Prep
│   │   │   ├── search.py      # Knowledge Search
│   │   │   ├── capture.py     # Quick Capture
│   │   │   └── manage.py      # Manage (CRUD)
│   │   ├── confirm.py         # Confirm Node
│   │   └── summarize.py       # Summarize Node
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py           # Conversation memory + profile
│   ├── data_layer/
│   │   ├── __init__.py
│   │   ├── loader.py          # JSON/Markdown loading
│   │   └── vector_store.py    # ChromaDB wrapper
│   ├── chainlit_app.py        # Chainlit UI entry
│   └── feishu_plugin.py       # Feishu Bot plugin
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_tools/
    │   ├── __init__.py
    │   ├── test_todos.py
    │   ├── test_notes.py
    │   ├── test_rag.py
    │   └── test_calendar.py
    ├── test_agent/
    │   ├── __init__.py
    │   ├── test_router.py
    │   ├── test_planning.py
    │   ├── test_prep.py
    │   ├── test_search.py
    │   ├── test_capture.py
    │   ├── test_manage.py
    │   └── test_graph.py
    ├── test_memory/
    │   ├── __init__.py
    │   └── test_store.py
    └── test_protocol.py
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create venv and install dependencies**

Run:
```bash
cd /Users/kang/Code/AgentPlan && python3 -m venv venv && source venv/bin/activate && pip install -e ".[dev]"
```

- [ ] **Step 3: Write .env.example**

```env
# LLM
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Google Calendar (optional — mock fallback if not set)
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json
GOOGLE_CALENDAR_ID=primary

# ChromaDB
CHROMA_PERSIST_DIR=data/chroma

# Data
DATA_DIR=data
```

- [ ] **Step 4: Write .gitignore**

```
__pycache__/
*.pyc
.env
credentials.json
data/chroma/
venv/
.superpowers/
```

- [ ] **Step 5: Write src/__init__.py**

```python
"""Polaris — Personal Efficiency AI Agent."""
```

- [ ] **Step 6: Write src/config.py**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma"))
NOTES_DIR = DATA_DIR / "notes"
ARCHIVE_DIR = NOTES_DIR / "archive"
CALENDAR_FILE = DATA_DIR / "calendar.json"
TODOS_FILE = DATA_DIR / "todos.json"
PROFILE_FILE = DATA_DIR / "user_profile.json"

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

GCAL_CREDENTIALS = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH")
GCAL_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
```

- [ ] **Step 7: Write tests/__init__.py** (empty)

- [ ] **Step 8: Write tests/conftest.py**

```python
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
```

- [ ] **Step 9: Create data directory and seed files**

Run:
```bash
mkdir -p /Users/kang/Code/AgentPlan/data/notes/archive
```

- [ ] **Step 10: Write seed data files**

Write `data/calendar.json`:
```json
[
  {
    "date": "2026-05-04",
    "events": [
      {"id": "evt-1", "time": "09:00", "title": "晨会", "attendees": ["Alice", "Bob"], "duration": 30},
      {"id": "evt-2", "time": "15:00", "title": "产品方案评审", "attendees": ["张三", "李四", "王五"], "duration": 60},
      {"id": "evt-3", "time": "17:00", "title": "周报同步", "attendees": ["全组"], "duration": 30}
    ]
  }
]
```

Write `data/todos.json`:
```json
[
  {"id": "todo-1", "title": "完成权限设计文档", "priority": "high", "status": "pending", "due": "2026-05-05", "tags": ["产品", "文档"]},
  {"id": "todo-2", "title": "Code Review PR #42", "priority": "medium", "status": "in_progress", "due": "2026-05-03", "tags": ["开发"]},
  {"id": "todo-3", "title": "准备周五技术分享", "priority": "medium", "status": "pending", "due": "2026-05-08", "tags": ["分享"]},
  {"id": "todo-4", "title": "更新 README", "priority": "low", "status": "done", "due": "2026-04-28", "tags": ["文档"]}
]
```

Write `data/user_profile.json`:
```json
{
  "name": "User",
  "preferred_working_hours": "9:00-18:00",
  "timezone": "Asia/Shanghai"
}
```

Write `data/notes/sample-meeting.md`:
```markdown
---
title: "PRD v2 讨论"
tags: ["产品", "评审"]
date: "2026-04-15"
---

讨论了用户权限方案细节。
决定采用 RBAC 模型实现权限控制。
张三提出需要支持多租户隔离。
待确认：多租户方案是否放在 v2 还是推迟到 v3。

## 结论
- 权限模型：RBAC
- 开发周期：2 周
- 负责人：李四
```

- [ ] **Step 11: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git init && git add -A && git commit -m "feat: project scaffold with venv, config, and seed data"
```

---

### Task 2: Message Protocol + AgentState

**Files:**
- Create: `src/protocol.py`
- Create: `src/state.py`
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Write failing tests for protocol**

Write `tests/test_protocol.py`:
```python
from src.protocol import AgentRequest, AgentResponse
from src.state import AgentState


def test_agent_request_creation():
    req = AgentRequest(message="今天有什么安排", session_id="sess-123")
    assert req.message == "今天有什么安排"
    assert req.session_id == "sess-123"


def test_agent_response_creation():
    resp = AgentResponse(response="你今天有3个会议", steps=["router: daily_planning", "tool: calendar_query"])
    assert resp.response == "你今天有3个会议"
    assert len(resp.steps) == 2


def test_agent_state_defaults():
    state = AgentState(
        messages=[],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    assert state["intent"] == ""
    assert state["pending_action"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_protocol.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write src/protocol.py**

```python
from dataclasses import dataclass, field


@dataclass
class AgentRequest:
    message: str
    session_id: str


@dataclass
class AgentResponse:
    response: str
    steps: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Write src/state.py**

```python
from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class PendingAction(TypedDict, total=False):
    action_type: str  # "create" | "update" | "delete"
    target_tool: str  # "calendar" | "todo" | "notes"
    target_id: str
    description: str
    params: dict


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    user_profile: dict
    tool_results: dict
    final_response: str
    needs_clarification: bool
    pending_action: Optional[dict]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_protocol.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/protocol.py src/state.py tests/test_protocol.py && git commit -m "feat: message protocol and AgentState types"
```

---

### Task 3: Data Loader

**Files:**
- Create: `src/data_layer/__init__.py`
- Create: `src/data_layer/loader.py`
- Create: `tests/test_data_layer/__init__.py`

- [ ] **Step 1: Write data loader**

Write `src/data_layer/__init__.py` (empty).

Write `src/data_layer/loader.py`:
```python
import json
import re
import yaml
from pathlib import Path
from datetime import date, datetime
from typing import Optional


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.suffix == ".json" and "profile" in path.name else []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_calendar_events(path: Path, target_date: Optional[str] = None) -> list[dict]:
    data = load_json(path)
    if not isinstance(data, list):
        return []
    if target_date:
        return [ev for day in data if day.get("date") == target_date for ev in day.get("events", [])]
    return [ev for day in data for ev in day.get("events", [])]


def save_calendar_event(path: Path, date_str: str, event: dict) -> None:
    data = load_json(path)
    if not isinstance(data, list):
        data = []
    for day in data:
        if day.get("date") == date_str:
            day.setdefault("events", []).append(event)
            save_json(path, data)
            return
    data.append({"date": date_str, "events": [event]})
    save_json(path, data)


def delete_calendar_event(path: Path, event_id: str) -> bool:
    data = load_json(path)
    for day in data:
        events = day.get("events", [])
        for i, ev in enumerate(events):
            if ev.get("id") == event_id:
                events.pop(i)
                save_json(path, data)
                return True
    return False


def load_todos(path: Path) -> list[dict]:
    data = load_json(path)
    return data if isinstance(data, list) else []


def save_todos(path: Path, todos: list[dict]) -> None:
    save_json(path, todos)


def parse_note_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown note. Returns (metadata, body)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()
    return {}, content.strip()


def format_note_file(metadata: dict, body: str) -> str:
    frontmatter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def load_notes(notes_dir: Path) -> list[dict]:
    results = []
    if not notes_dir.exists():
        return results
    for md_file in notes_dir.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_note_frontmatter(content)
        results.append({"path": str(md_file), "filename": md_file.name, "metadata": meta, "content": body})
    return results


def save_note(notes_dir: Path, title: str, body: str, tags: list[str] | None = None) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
    filename = f"{slug}.md"
    filepath = notes_dir / filename
    metadata = {"title": title, "tags": tags or [], "date": date.today().isoformat()}
    content = format_note_file(metadata, body)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def archive_note(filepath: Path, archive_dir: Path) -> bool:
    if not filepath.exists():
        return False
    archive_dir.mkdir(parents=True, exist_ok=True)
    filepath.rename(archive_dir / filepath.name)
    return True
```

- [ ] **Step 2: Verify with a quick smoke test**

Run:
```bash
cd /Users/kang/Code/AgentPlan && python -c "
from src.data_layer.loader import load_notes, load_calendar_events, parse_note_frontmatter
from src.config import DATA_DIR

events = load_calendar_events(DATA_DIR / 'calendar.json', '2026-05-04')
print(f'Events on 2026-05-04: {len(events)}')

notes = load_notes(DATA_DIR / 'notes')
print(f'Notes: {len(notes)}')
for n in notes:
    print(f'  - {n[\"metadata\"].get(\"title\")}')
"
```

Expected: `Events on 2026-05-04: 3`, `Notes: 1`

- [ ] **Step 3: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/data_layer/ tests/test_data_layer/ && git commit -m "feat: data loader with JSON/Markdown read/write"
```

---

### Task 4: TodoTool (CRUD)

**Files:**
- Create: `src/tools/__init__.py`
- Create: `src/tools/registry.py`
- Create: `src/tools/todos.py`
- Test: `tests/test_tools/__init__.py`
- Test: `tests/test_tools/test_todos.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_tools/__init__.py` (empty).

Write `tests/test_tools/test_todos.py`:
```python
import json
from src.tools.todos import TodoTool


def test_todo_list_all(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("list all")
    assert "完成权限设计文档" in result


def test_todo_list_pending(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("list pending")
    assert "完成权限设计文档" in result


def test_todo_search(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("search 权限")
    assert "完成权限设计文档" in result


def test_todo_create(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run('create {"title": "新待办", "priority": "high", "due": "2026-05-10"}')
    assert "新待办" in result
    # Verify persisted
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert any(t["title"] == "新待办" for t in data)


def test_todo_mark_done(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("done todo-1")
    assert "已完成" in result.lower() or "done" in result.lower()


def test_todo_delete(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("delete todo-1")
    assert "已删除" in result.lower() or "deleted" in result.lower()
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert not any(t["id"] == "todo-1" for t in data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_todos.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write ToolRegistry**

Write `src/tools/__init__.py` (empty).

Write `src/tools/registry.py`:
```python
from langchain_core.tools import BaseTool
from typing import Optional


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

- [ ] **Step 4: Write TodoTool**

Write `src/tools/todos.py`:
```python
import json
import uuid
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class TodoInput(BaseModel):
    command: str = Field(description="Command: 'list [status]', 'search <keyword>', 'create <json>', 'done <id>', 'delete <id>'")
    # ^ Squashed into one string param for LangChain tool calling compatibility


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = "Manage todo items. Commands: list all|pending|done, search <keyword>, create {\"title\":...,\"priority\":...,\"due\":...}, done <todo_id>, delete <todo_id>"
    data_file: str = ""

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_todos, save_json
        from pathlib import Path

        path = Path(self.data_file)
        todos = load_todos(path)
        cmd = command.strip().lower()

        if cmd.startswith("list"):
            status_filter = cmd.replace("list", "").strip()
            if status_filter and status_filter != "all":
                todos = [t for t in todos if t.get("status") == status_filter]
            if not todos:
                return "没有待办事项。"
            lines = []
            for t in todos:
                status_icon = {"pending": "○", "in_progress": "◉", "done": "✓"}.get(t.get("status", ""), "?")
                lines.append(f"- {status_icon} [{t.get('priority', '-')}] {t['title']} (截止: {t.get('due', '无')}) [ID: {t['id']}]")
            return "\n".join(lines)

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            if not keyword:
                return "请提供搜索关键词。"
            matches = [t for t in todos if keyword.lower() in t.get("title", "").lower() or keyword.lower() in " ".join(t.get("tags", [])).lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的待办。"
            return "\n".join(f"- [{t['priority']}] {t['title']} [ID: {t['id']}]" for t in matches)

        elif cmd.startswith("create"):
            try:
                json_str = command.split("create", 1)[1].strip()
                new_todo = json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                return "创建待办需要 JSON 格式：create {\"title\": \"...\", \"priority\": \"high|medium|low\", \"due\": \"YYYY-MM-DD\"}"
            new_todo["id"] = f"todo-{uuid.uuid4().hex[:8]}"
            new_todo.setdefault("status", "pending")
            new_todo.setdefault("tags", [])
            todos.append(new_todo)
            save_json(path, todos)
            return f"已添加待办：{new_todo['title']} [ID: {new_todo['id']}]"

        elif cmd.startswith("done"):
            todo_id = cmd.replace("done", "").strip()
            for t in todos:
                if t["id"] == todo_id:
                    t["status"] = "done"
                    save_json(path, todos)
                    return f"已将「{t['title']}」标记为已完成。"
            return f"未找到待办 ID: {todo_id}"

        elif cmd.startswith("delete"):
            todo_id = cmd.replace("delete", "").strip()
            for i, t in enumerate(todos):
                if t["id"] == todo_id:
                    title = t["title"]
                    todos.pop(i)
                    save_json(path, todos)
                    return f"已删除待办：{title}"
            return f"未找到待办 ID: {todo_id}"

        else:
            return "可用命令：list [status], search <keyword>, create <json>, done <id>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_todos.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/tools/ tests/test_tools/ && git commit -m "feat: TodoTool with full CRUD"
```

---

### Task 5: NoteTool

**Files:**
- Create: `src/tools/notes.py`
- Test: `tests/test_tools/test_notes.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_tools/test_notes.py`:
```python
from src.tools.notes import NoteTool


def test_note_list(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run("list")
    assert "PRD v2 讨论" in result


def test_note_read(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run("read prd-v2-discussion.md")
    assert "RBAC" in result


def test_note_create(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run('create {"title": "测试笔记", "content": "这是一条测试内容", "tags": ["test"]}')
    assert "已记录" in result or "已创建" in result
    # Verify file created
    created = list((tmp_data_dir / "notes").glob("*.md"))
    assert any("测试笔记" in f.read_text(encoding="utf-8") for f in created)


def test_note_archive(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run("archive prd-v2-discussion.md")
    assert "已归档" in result.lower() or "archived" in result.lower()


def test_note_search(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run("search RBAC")
    assert "PRD v2 讨论" in result or "RBAC" in result
```

- [ ] **Step 2: Run tests — expect fail**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_notes.py -v`
Expected: FAIL

- [ ] **Step 3: Write NoteTool**

Write `src/tools/notes.py`:
```python
import json
from langchain_core.tools import BaseTool
from pathlib import Path


class NoteTool(BaseTool):
    name: str = "notes"
    description: str = "Manage notes. Commands: list, read <filename>, create {\"title\":...,\"content\":...,\"tags\":[...]}, search <keyword>, archive <filename>"
    notes_dir: str = ""
    archive_dir: str = ""

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_notes, save_note, archive_note

        notes_path = Path(self.notes_dir)
        archive_path = Path(self.archive_dir)
        cmd = command.strip().lower()

        if cmd == "list":
            notes = load_notes(notes_path)
            if not notes:
                return "没有笔记。"
            return "\n".join(f"- {n['metadata'].get('title', n['filename'])} ({n['filename']})" for n in notes)

        elif cmd.startswith("read"):
            filename = command.split("read", 1)[1].strip()
            filepath = notes_path / filename
            if not filepath.exists():
                return f"笔记不存在：{filename}"
            content = filepath.read_text(encoding="utf-8")
            return content

        elif cmd.startswith("create"):
            try:
                json_str = command.split("create", 1)[1].strip()
                data = json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                return "创建笔记需要 JSON：create {\"title\":\"...\", \"content\":\"...\", \"tags\":[...]}"
            filepath = save_note(notes_path, data["title"], data.get("content", ""), data.get("tags"))
            return f"已记录笔记：{data['title']} ({filepath.name})"

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            notes = load_notes(notes_path)
            matches = [n for n in notes if keyword.lower() in n["content"].lower() or keyword.lower() in n["metadata"].get("title", "").lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的笔记。"
            return "\n\n".join(f"## {n['metadata'].get('title', n['filename'])}\n{n['content'][:300]}" for n in matches)

        elif cmd.startswith("archive"):
            filename = command.replace("archive", "").strip()
            filepath = notes_path / filename
            if archive_note(filepath, archive_path):
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        else:
            return "可用命令：list, read <filename>, create <json>, search <keyword>, archive <filename>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_notes.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/tools/notes.py tests/test_tools/test_notes.py && git commit -m "feat: NoteTool with create/read/search/archive"
```

---

### Task 6: RAGSearchTool

**Files:**
- Create: `src/data_layer/vector_store.py`
- Create: `src/tools/rag.py`
- Test: `tests/test_tools/test_rag.py`

- [ ] **Step 1: Write failing test**

Write `tests/test_tools/test_rag.py`:
```python
import pytest
from src.tools.rag import RAGSearchTool
from src.data_layer.vector_store import get_vector_store, index_notes


@pytest.fixture
def rag_tool(tmp_data_dir):
    chroma_dir = str(tmp_data_dir / "chroma")
    notes_dir = str(tmp_data_dir / "notes")
    index_notes(notes_dir, chroma_dir, "test-collection")
    return RAGSearchTool(persist_dir=chroma_dir, collection_name="test-collection")


def test_rag_search_finds_note(rag_tool):
    result = rag_tool._run("权限方案")
    assert "RBAC" in result or "权限" in result


def test_rag_search_no_match(rag_tool):
    result = rag_tool._run("量子计算")
    assert "没有找到" in result or "无关" in result
```

- [ ] **Step 2: Write vector_store.py**

Write `src/data_layer/vector_store.py`:
```python
from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils import embedding_functions


def get_embedding_function():
    """Use OpenAI embeddings. Falls back to a simple local model if no API key."""
    import os
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key and api_key != "sk-placeholder":
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small"
        )
    # Fallback: use sentence-transformers (install with: pip install sentence-transformers)
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def get_vector_store(persist_dir: str, collection_name: str = "notes"):
    client = PersistentClient(path=persist_dir)
    embedding = get_embedding_function()
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding,
    )


def index_notes(notes_dir: str, persist_dir: str, collection_name: str = "notes") -> None:
    """Index all markdown notes into ChromaDB. Call this on startup and after note changes."""
    from src.data_layer.loader import load_notes

    collection = get_vector_store(persist_dir, collection_name)
    notes = load_notes(Path(notes_dir))

    # Clear and rebuild for simplicity (ok for small personal collections)
    existing_ids = set(collection.get()["ids"])
    new_ids = set()

    for note in notes:
        note_id = note["filename"].replace(".md", "").replace(" ", "-")
        new_ids.add(note_id)
        if note_id in existing_ids:
            continue  # Already indexed
        collection.add(
            ids=[note_id],
            documents=[note["content"]],
            metadatas=[{"title": note["metadata"].get("title", ""), "tags": ",".join(note["metadata"].get("tags", []))}],
        )

    # Remove deleted notes from index
    for old_id in existing_ids - new_ids:
        collection.delete(ids=[old_id])


def search_notes(query: str, persist_dir: str, collection_name: str = "notes", top_k: int = 3) -> list[dict]:
    collection = get_vector_store(persist_dir, collection_name)
    results = collection.query(query_texts=[query], n_results=top_k)
    output = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 0
            output.append({"content": doc, "metadata": meta, "distance": dist})
    return output
```

- [ ] **Step 3: Write RAGSearchTool**

Write `src/tools/rag.py`:
```python
from langchain_core.tools import BaseTool


class RAGSearchTool(BaseTool):
    name: str = "rag_search"
    description: str = "Semantic search across your notes. Input: a natural language query string."
    persist_dir: str = ""
    collection_name: str = "notes"

    def _run(self, query: str) -> str:
        from src.data_layer.vector_store import search_notes

        query = query.strip()
        if not query:
            return "请输入搜索内容。"

        results = search_notes(query, self.persist_dir, self.collection_name)

        if not results:
            return "没有找到相关笔记。"

        output = []
        for r in results:
            similarity = max(0, 1 - r["distance"]) if r["distance"] else 1.0
            if similarity < 0.3:
                continue
            title = r["metadata"].get("title", "未命名")
            output.append(f"## {title} (相关度: {similarity:.0%})\n{r['content'][:500]}")

        if not output:
            return "没有找到足够相关的笔记，可以换个关键词试试？"

        return "\n\n---\n\n".join(output)

    async def _arun(self, query: str) -> str:
        return self._run(query)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_rag.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/data_layer/vector_store.py src/tools/rag.py tests/test_tools/test_rag.py && git commit -m "feat: RAGSearchTool with ChromaDB vector search"
```

---

### Task 7: GoogleCalendarTool

**Files:**
- Create: `src/tools/calendar.py`
- Test: `tests/test_tools/test_calendar.py`

- [ ] **Step 1: Write failing test**

Write `tests/test_tools/test_calendar.py`:
```python
import json
from src.tools.calendar import GoogleCalendarTool


def test_calendar_list_date(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("list 2026-05-03")
    assert "晨会" in result
    assert "产品评审" in result


def test_calendar_create_event(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run('create {"date":"2026-05-05","time":"14:00","title":"测试会议"}')
    assert "已添加" in result


def test_calendar_search(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("search 产品评审")
    assert "产品评审" in result


def test_calendar_delete(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("delete evt-1")
    assert "已删除" in result.lower() or "已取消" in result.lower()
```

- [ ] **Step 2: Write GoogleCalendarTool**

Write `src/tools/calendar.py`:
```python
import json
import uuid
from langchain_core.tools import BaseTool
from pathlib import Path


class GoogleCalendarTool(BaseTool):
    name: str = "calendar"
    description: str = (
        "Manage calendar events. Commands: "
        "list <date YYYY-MM-DD>, "
        "create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\",\"attendees\":[...]}, "
        "search <keyword>, "
        "update <event_id> {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}, "
        "delete <event_id>"
    )
    data_file: str = ""
    use_mock: bool = True

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_json, save_json

        path = Path(self.data_file)
        cmd = command.strip().lower()

        if cmd.startswith("list"):
            date_str = command.split("list", 1)[1].strip()
            data = load_json(path) if isinstance(load_json(path), list) else []
            for day in data:
                if day.get("date") == date_str:
                    events = day.get("events", [])
                    if not events:
                        return f"{date_str} 没有日程安排。"
                    return "\n".join(
                        f"- {ev['time']} {ev['title']} ({ev.get('duration', 60)}分钟) [ID: {ev['id']}]"
                        for ev in sorted(events, key=lambda e: e.get("time", ""))
                    )
            return f"{date_str} 没有日程安排。"

        elif cmd.startswith("create"):
            try:
                json_str = command.split("create", 1)[1].strip()
                new_event = json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                return "创建日程需要 JSON：create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}"
            new_event["id"] = f"evt-{uuid.uuid4().hex[:8]}"
            new_event.setdefault("duration", 60)
            new_event.setdefault("attendees", [])

            data = load_json(path) if isinstance(load_json(path), list) else []
            date_str = new_event.pop("date")
            for day in data:
                if day.get("date") == date_str:
                    day.setdefault("events", []).append(new_event)
                    save_json(path, data)
                    return f"已添加日程：{date_str} {new_event.get('time','')} {new_event['title']} [ID: {new_event['id']}]"
            data.append({"date": date_str, "events": [new_event]})
            save_json(path, data)
            return f"已添加日程：{date_str} {new_event.get('time','')} {new_event['title']} [ID: {new_event['id']}]"

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            data = load_json(path) if isinstance(load_json(path), list) else []
            matches = []
            for day in data:
                for ev in day.get("events", []):
                    if keyword.lower() in ev.get("title", "").lower():
                        matches.append((day["date"], ev))
            if not matches:
                return f"没有找到包含「{keyword}」的日程。"
            return "\n".join(f"- {date}: {ev['time']} {ev['title']} [ID: {ev['id']}]" for date, ev in matches)

        elif cmd.startswith("update"):
            parts = command.split(None, 2)
            if len(parts) < 3:
                return "用法: update <event_id> {\"date\":\"...\",\"time\":\"...\"}"
            event_id = parts[1]
            try:
                update_data = json.loads(parts[2])
            except json.JSONDecodeError:
                return "更新数据需要 JSON 格式"

            data = load_json(path) if isinstance(load_json(path), list) else []
            for day in data:
                for ev in day.get("events", []):
                    if ev["id"] == event_id:
                        ev.update(update_data)
                        save_json(path, data)
                        return f"已更新日程：{ev.get('title', event_id)}"
            return f"未找到日程 ID: {event_id}"

        elif cmd.startswith("delete"):
            event_id = cmd.replace("delete", "").strip()
            data = load_json(path) if isinstance(load_json(path), list) else []
            for day in data:
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    if ev["id"] == event_id:
                        title = ev["title"]
                        events.pop(i)
                        save_json(path, data)
                        return f"已删除日程：{title}"
            return f"未找到日程 ID: {event_id}"

        else:
            return "可用命令：list <date>, create <json>, search <keyword>, update <id> <json>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_tools/test_calendar.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/tools/calendar.py tests/test_tools/test_calendar.py && git commit -m "feat: GoogleCalendarTool with CRUD (mock mode)"
```

---

### Task 8: Memory Store

**Files:**
- Create: `src/memory/__init__.py`
- Create: `src/memory/store.py`
- Test: `tests/test_memory/__init__.py`
- Test: `tests/test_memory/test_store.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_memory/__init__.py` (empty).

Write `tests/test_memory/test_store.py`:
```python
from langchain_core.messages import HumanMessage, AIMessage
from src.memory.store import MemoryManager


def test_memory_add_and_retrieve():
    mm = MemoryManager(window_size=4)
    mm.add_message(HumanMessage(content="今天有什么安排"))
    mm.add_message(AIMessage(content="你今天有3个会议"))
    history = mm.get_history()
    assert len(history) == 2
    assert history[0].content == "今天有什么安排"


def test_memory_window_limit():
    mm = MemoryManager(window_size=2)
    mm.add_message(HumanMessage(content="msg1"))
    mm.add_message(AIMessage(content="msg2"))
    mm.add_message(HumanMessage(content="msg3"))
    history = mm.get_history()
    assert len(history) == 2
    assert history[0].content == "msg2"


def test_memory_load_profile(tmp_data_dir):
    mm = MemoryManager(window_size=4, profile_path=str(tmp_data_dir / "user_profile.json"))
    profile = mm.get_profile()
    assert profile["name"] == "TestUser"


def test_memory_update_profile(tmp_data_dir):
    mm = MemoryManager(window_size=4, profile_path=str(tmp_data_dir / "user_profile.json"))
    mm.update_profile({"preferred_working_hours": "10:00-19:00"})
    profile = mm.get_profile()
    assert profile["preferred_working_hours"] == "10:00-19:00"
```

- [ ] **Step 2: Write MemoryManager**

Write `src/memory/__init__.py` (empty).

Write `src/memory/store.py`:
```python
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import BaseMessage
from pathlib import Path
from typing import Optional


class MemoryManager:
    def __init__(self, window_size: int = 10, profile_path: Optional[str] = None):
        self.memory = ConversationBufferWindowMemory(
            return_messages=True,
            k=window_size,
            memory_key="messages",
        )
        self.profile_path = Path(profile_path) if profile_path else None
        self._profile: dict = {}

    def add_message(self, message: BaseMessage) -> None:
        self.memory.chat_memory.add_message(message)

    def get_history(self) -> list[BaseMessage]:
        return self.memory.chat_memory.messages

    def get_profile(self) -> dict:
        if not self._profile and self.profile_path and self.profile_path.exists():
            import json
            self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        return self._profile

    def update_profile(self, updates: dict) -> None:
        self._profile.update(updates)
        if self.profile_path:
            import json
            self.profile_path.write_text(json.dumps(self._profile, ensure_ascii=False, indent=2), encoding="utf-8")

    def format_history_as_string(self) -> str:
        lines = []
        for msg in self.get_history():
            role = "用户" if msg.type == "human" else "助手"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_memory/test_store.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/memory/ tests/test_memory/ && git commit -m "feat: MemoryManager with windowed conversation history and profile"
```

---

### Task 9: Agent Router Node

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/agent/router.py`
- Test: `tests/test_agent/__init__.py`
- Test: `tests/test_agent/test_router.py`

- [ ] **Step 1: Write failing test**

Write `tests/test_agent/__init__.py` (empty).

Write `tests/test_agent/test_router.py`:
```python
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from src.agent.router import classify_intent
from src.state import AgentState


def make_state(message: str) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=message)],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )


def test_router_daily_planning():
    state = make_state("今天有什么安排")
    result = classify_intent(state)
    assert result["intent"] == "daily_planning"


def test_router_meeting_prep():
    state = make_state("下午3点的会帮我准备一下")
    result = classify_intent(state)
    assert result["intent"] == "meeting_prep"


def test_router_knowledge_search():
    state = make_state("上次RBAC的讨论结果是什么")
    result = classify_intent(state)
    assert result["intent"] == "knowledge_search"


def test_router_quick_capture_calendar():
    state = make_state("明天下午3点加个产品评审会")
    result = classify_intent(state)
    assert result["intent"] == "quick_capture"


def test_router_quick_capture_note():
    state = make_state("记一下，RBAC方案选了角色继承模型")
    result = classify_intent(state)
    assert result["intent"] == "quick_capture"


def test_router_manage():
    state = make_state("取消明天的产品评审")
    result = classify_intent(state)
    assert result["intent"] == "manage"
```

- [ ] **Step 2: Write Router**

Write `src/agent/__init__.py` (empty).

Write `src/agent/router.py`:
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

INTENT_OPTIONS = ["daily_planning", "meeting_prep", "knowledge_search", "quick_capture", "manage", "clarify"]

ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个意图分类器。分析用户消息，输出一个意图标签。

意图说明：
- daily_planning: 询问今日/某天的日程安排、待办、计划
- meeting_prep: 为某个会议做准备、整理材料
- knowledge_search: 搜索历史笔记、查找之前记录的信息
- quick_capture: 快速记录/创建日程、笔记、待办（用户想添加/记录新东西）
- manage: 修改、取消、删除已有的日程或待办（用户想改动现有东西）
- clarify: 消息信息不足，无法判断意图

区分 quick_capture 和 manage 的关键：
- "加个"、"新建"、"记一下"、"创建"、"添加" → quick_capture
- "取消"、"删除"、"修改"、"改到"、"改成"、"标记为" → manage

只输出意图标签，不要解释。"""),
    ("human", "{message}"),
])


def classify_intent(state: AgentState) -> dict:
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "clarify"}

    last_message = messages[-1]
    content = last_message.content if hasattr(last_message, "content") else str(last_message)

    # Simple keyword-based routing as first pass (cheap + reliable for obvious cases)
    intent = _keyword_route(content)
    if intent:
        return {"intent": intent}

    # Fallback to LLM classification
    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
    chain = ROUTER_PROMPT | llm
    result = chain.invoke({"message": content})
    intent = result.content.strip().lower()

    if intent not in INTENT_OPTIONS:
        intent = "clarify"

    return {"intent": intent}


def _keyword_route(content: str) -> str | None:
    content_lower = content.strip().lower()

    create_keywords = ["加个", "新建", "记一下", "添加", "创建", "帮我加", "帮我记", "记录一下", "写个笔记"]
    for kw in create_keywords:
        if kw in content_lower:
            return "quick_capture"

    manage_keywords = ["取消", "删除", "改到", "改成", "更新", "标记为", "移除", "清理"]
    for kw in manage_keywords:
        if kw in content_lower:
            return "manage"

    search_keywords = ["上次", "之前", "讨论过", "讨论了什么", "找一下", "搜索", "查一下笔记", "有没有记"]
    for kw in search_keywords:
        if kw in content_lower:
            return "knowledge_search"

    planning_keywords = ["安排", "计划", "今天有什么", "今天干嘛", "日程", "有什么事情", "今天要做"]
    for kw in planning_keywords:
        if kw in content_lower:
            return "daily_planning"

    prep_keywords = ["准备", "会议材料", "帮我准备"]
    for kw in prep_keywords:
        if kw in content_lower:
            return "meeting_prep"

    return None


def route_condition(state: AgentState) -> str:
    return state.get("intent", "clarify")
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_agent/test_router.py -v`
Expected: 6 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/agent/ tests/test_agent/ && git commit -m "feat: Router node with keyword fast-path + LLM classification"
```

---

### Task 10: Skill Subgraphs — Planning & Search

**Files:**
- Create: `src/agent/skills/__init__.py`
- Create: `src/agent/skills/planning.py`
- Create: `src/agent/skills/search.py`
- Test: `tests/test_agent/test_planning.py`
- Test: `tests/test_agent/test_search.py`

- [ ] **Step 1: Write Planning skill**

Write `src/agent/skills/__init__.py` (empty).

Write `src/agent/skills/planning.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def planning_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # Build a prompt with tool instructions
    prompt = f"""你是每日规划助手。用户的问题是：
"{last_msg}"

请按以下步骤操作，用对应命令调用工具：
1. 查看当日日历：calendar list <今天日期>
2. 查看待办：todo list pending

然后根据返回结果，生成今日计划。日历事件按时段排列，待办按优先级排列。
如果事件和待办截止时间冲突，标注冲突。"""

    return {
        "tool_results": {"planning_prompt": prompt},
        "final_response": "",  # Will be filled by summarize node
    }


def create_planning_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("planning", planning_node)
    builder.set_entry_point("planning")
    builder.add_edge("planning", END)
    return builder.compile()
```

- [ ] **Step 2: Write Search skill**

Write `src/agent/skills/search.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def search_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    prompt = f"""你是知识检索助手。用户想查找：
"{last_msg}"

请使用 RAG 搜索工具查找相关笔记：
rag_search <用户的查询关键词>

如果搜索结果不够相关（相关度 < 30%），请告诉用户未找到，并追问更具体的关键词。"""

    return {
        "tool_results": {"search_prompt": prompt},
        "final_response": "",
    }


def create_search_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("search", search_node)
    builder.set_entry_point("search")
    builder.add_edge("search", END)
    return builder.compile()
```

- [ ] **Step 3: Write tests**

Write `tests/test_agent/test_planning.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.planning import planning_node
from src.state import AgentState


def test_planning_node_produces_prompt():
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="daily_planning",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    result = planning_node(state)
    assert "tool_results" in result
    assert "planning_prompt" in result["tool_results"]
    assert "今天" in result["tool_results"]["planning_prompt"]
```

Write `tests/test_agent/test_search.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.search import search_node
from src.state import AgentState


def test_search_node_produces_prompt():
    state = AgentState(
        messages=[HumanMessage(content="上次RBAC讨论的结果")],
        intent="knowledge_search",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    result = search_node(state)
    assert "search_prompt" in result["tool_results"]
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_agent/test_planning.py tests/test_agent/test_search.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/agent/skills/ tests/test_agent/test_planning.py tests/test_agent/test_search.py && git commit -m "feat: Planning and Search skill subgraphs"
```

---

### Task 11: Skill Subgraphs — Prep, Capture, Manage

**Files:**
- Create: `src/agent/skills/prep.py`
- Create: `src/agent/skills/capture.py`
- Create: `src/agent/skills/manage.py`
- Test: `tests/test_agent/test_prep.py`
- Test: `tests/test_agent/test_capture.py`
- Test: `tests/test_agent/test_manage.py`

- [ ] **Step 1: Write Prep skill**

Write `src/agent/skills/prep.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def prep_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    prompt = f"""你是会前准备助手。用户说：
"{last_msg}"

请按以下步骤操作：
1. 查找会议：calendar search <会议关键词>
2. 搜索相关笔记：rag_search <会议主题关键词>
3. 检查关联待办：todo search <会议关键词>

汇总会议信息、相关笔记摘要、关联待办，生成一份会议准备清单。"""

    return {"tool_results": {"prep_prompt": prompt}, "final_response": ""}


def create_prep_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("prep", prep_node)
    builder.set_entry_point("prep")
    builder.add_edge("prep", END)
    return builder.compile()
```

- [ ] **Step 2: Write Capture skill**

Write `src/agent/skills/capture.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def capture_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    prompt = f"""你是快速记录助手。用户说：
"{last_msg}"

请判断用户想记录什么类型的内容，并调用对应工具：

- 如果是日程（含时间/日期信息）：calendar create {{"date":"YYYY-MM-DD","time":"HH:MM","title":"...","attendees":[...]}}
- 如果是笔记（信息/想法/结论）：notes create {{"title":"...","content":"...","tags":[...]}}
- 如果是待办（任务/事项）：todo create {{"title":"...","priority":"high|medium|low","due":"YYYY-MM-DD"}}

提取结构化信息后执行创建。注意将"明天"、"周五"等自然语言日期转换为具体日期。"""

    return {"tool_results": {"capture_prompt": prompt}, "final_response": ""}


def create_capture_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("capture", capture_node)
    builder.set_entry_point("capture")
    builder.add_edge("capture", END)
    return builder.compile()
```

- [ ] **Step 3: Write Manage skill**

Write `src/agent/skills/manage.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def manage_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    prompt = f"""你是信息管理助手。用户说：
"{last_msg}"

请判断操作类型：
- 查询/搜索：先用对应工具的 search 命令找到目标
- 修改：用 update 命令，先回显确认再执行
- 删除/取消：用 delete 命令，先回显确认再执行
- 标记完成：todo done <id>

**重要**：对于修改和删除操作，先在回复中说明将要执行的操作，等待用户确认后才能执行。
确认格式："找到：[资源描述]。确认执行此操作？"

如果用户已确认（上一条消息是"确认"或"是"），则执行 pending_action 中的操作。"""

    return {"tool_results": {"manage_prompt": prompt}, "final_response": ""}


def create_manage_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("manage", manage_node)
    builder.set_entry_point("manage")
    builder.add_edge("manage", END)
    return builder.compile()
```

- [ ] **Step 4: Write tests**

Write `tests/test_agent/test_prep.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.prep import prep_node
from src.state import AgentState


def test_prep_node():
    state = AgentState(
        messages=[HumanMessage(content="下午3点的会帮我准备")],
        intent="meeting_prep", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = prep_node(state)
    assert "prep_prompt" in result["tool_results"]
```

Write `tests/test_agent/test_capture.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.capture import capture_node
from src.state import AgentState


def test_capture_node():
    state = AgentState(
        messages=[HumanMessage(content="明天下午3点加个产品评审会")],
        intent="quick_capture", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = capture_node(state)
    assert "capture_prompt" in result["tool_results"]
```

Write `tests/test_agent/test_manage.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.manage import manage_node
from src.state import AgentState


def test_manage_node():
    state = AgentState(
        messages=[HumanMessage(content="取消明天的产品评审")],
        intent="manage", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = manage_node(state)
    assert "manage_prompt" in result["tool_results"]
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_agent/test_prep.py tests/test_agent/test_capture.py tests/test_agent/test_manage.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/agent/skills/prep.py src/agent/skills/capture.py src/agent/skills/manage.py tests/test_agent/test_prep.py tests/test_agent/test_capture.py tests/test_agent/test_manage.py && git commit -m "feat: Prep, Capture, and Manage skill subgraphs"
```

---

### Task 12: Confirm & Summarize Nodes + Graph Assembly

**Files:**
- Create: `src/agent/confirm.py`
- Create: `src/agent/summarize.py`
- Create: `src/agent/graph.py`
- Test: `tests/test_agent/test_graph.py`

- [ ] **Step 1: Write Confirm node**

Write `src/agent/confirm.py`:
```python
from src.state import AgentState


def confirm_node(state: AgentState) -> dict:
    pending = state.get("pending_action")
    if not pending:
        return {"final_response": "没有待确认的操作。", "pending_action": None}

    messages = state.get("messages", [])
    last_msg = messages[-1].content.strip() if messages else ""

    if last_msg in ("确认", "是", "yes", "好", "可以", "ok"):
        # Execute the pending action — caller (summarize node) will handle actual tool call
        return {"final_response": "", "pending_action": {**pending, "confirmed": True}}

    if last_msg in ("取消", "不", "no", "算了", "别"):
        return {"final_response": "已取消操作。", "pending_action": None}

    # Still waiting for confirmation
    return {"final_response": f"请确认：{pending.get('description', '执行此操作？')}（回复「确认」或「取消」）"}
```

- [ ] **Step 2: Write Summarize node**

Write `src/agent/summarize.py`:
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是个人效率助手 Polaris。根据工具执行结果，生成自然、有帮助的回复。

规则：
- 用中文回复
- 简洁直接，不要啰嗦
- 如果是日程列表，按时间排列
- 如果是笔记搜索结果，标注相关度
- 如果是创建/修改/删除确认，清晰说明操作内容

工具结果：
{tool_results}

对话历史：
{history}

用户最后说：{message}

请生成回复："""),
])


def summarize_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    tool_results = state.get("tool_results", {})
    history = "\n".join(
        f"{'用户' if m.type == 'human' else '助手'}: {m.content}"
        for m in messages[-6:]  # Last 6 messages for context
    )

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
    chain = SUMMARIZE_PROMPT | llm
    result = chain.invoke({
        "tool_results": str(tool_results),
        "history": history,
        "message": last_msg,
    })

    return {"final_response": result.content.strip()}
```

- [ ] **Step 3: Write Graph assembly**

Write `src/agent/graph.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.summarize import summarize_node
from src.agent.skills.planning import planning_node
from src.agent.skills.prep import prep_node
from src.agent.skills.search import search_node
from src.agent.skills.capture import capture_node
from src.agent.skills.manage import manage_node


def clarify_node(state: AgentState) -> dict:
    return {
        "final_response": "不太确定你想做什么，能再说详细一点吗？比如：\n- 「今天有什么安排」查看日程\n- 「下午3点的会帮我准备」会议准备\n- 「上次RBAC讨论了什么」搜索笔记\n- 「记一下：xxx」快速记录\n- 「取消明天的晨会」管理操作",
        "needs_clarification": False,
    }


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # Add all nodes
    builder.add_node("router", classify_intent)
    builder.add_node("clarify", clarify_node)
    builder.add_node("planning", planning_node)
    builder.add_node("prep", prep_node)
    builder.add_node("search", search_node)
    builder.add_node("capture", capture_node)
    builder.add_node("manage", manage_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("summarize", summarize_node)

    # Entry point
    builder.set_entry_point("router")

    # Conditional routing from router
    builder.add_conditional_edges(
        "router",
        route_condition,
        {
            "daily_planning": "planning",
            "meeting_prep": "prep",
            "knowledge_search": "search",
            "quick_capture": "capture",
            "manage": "manage",
            "clarify": "clarify",
        }
    )

    # All skill nodes go to summarize
    for node in ["planning", "prep", "search", "capture", "manage"]:
        builder.add_edge(node, "summarize")

    # Clarify goes direct to END (no tool results to summarize)
    builder.add_edge("clarify", END)

    # Summarize goes to END
    builder.add_edge("summarize", END)

    return builder.compile()


def get_agent():
    return build_agent_graph()
```

- [ ] **Step 4: Write graph integration test**

Write `tests/test_agent/test_graph.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


def test_graph_builds_successfully():
    graph = build_agent_graph()
    assert graph is not None


def test_graph_routes_to_clarify_for_empty_message():
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="...")],
        intent="",
        user_profile={},
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )
    # Graph should not raise on invoke
    result = graph.invoke(state)
    assert "final_response" in result
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/test_agent/test_graph.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/agent/confirm.py src/agent/summarize.py src/agent/graph.py tests/test_agent/test_graph.py && git commit -m "feat: Confirm node, Summarize node, and full graph assembly"
```

---

### Task 13: Chainlit Web UI

**Files:**
- Create: `src/chainlit_app.py`

- [ ] **Step 1: Write Chainlit app**

Write `src/chainlit_app.py`:
```python
"""Polaris Chainlit Web UI entry point.

Run with: chainlit run src/chainlit_app.py
"""

import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager

# In-memory session store (for prototype; use Redis/DB in production)
sessions: dict[str, MemoryManager] = {}


def get_or_create_memory(session_id: str) -> MemoryManager:
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(window_size=10)
    return sessions[session_id]


@cl.on_chat_start
async def start():
    await cl.Message(
        content="你好！我是 Polaris，你的个人效率助手。\n\n"
        "我可以帮你：\n"
        "- 🗓 **查看日程**：今天有什么安排？\n"
        "- 📋 **会议准备**：下午的会帮我准备\n"
        "- 🔍 **搜索笔记**：上次RBAC讨论了什么\n"
        "- ✍️ **快速记录**：记一下，明天开会要讨论权限方案\n"
        "- ✏️ **管理信息**：取消明天的晨会\n\n"
        "试试跟我说点什么吧！"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("id")
    memory = get_or_create_memory(session_id)

    agent = get_agent()

    # Build state
    memory.add_message(HumanMessage(content=message.content))
    state = AgentState(
        messages=memory.get_history(),
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )

    # Invoke agent
    result = agent.invoke(state)

    response = result.get("final_response", "抱歉，处理出错了。")
    memory.add_message(AIMessage(content=response))

    await cl.Message(content=response).send()
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/kang/Code/AgentPlan && python -c "from src.chainlit_app import get_agent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/chainlit_app.py && git commit -m "feat: Chainlit Web UI entry point"
```

---

### Task 14: Feishu Bot Plugin

**Files:**
- Create: `src/feishu_plugin.py`

- [ ] **Step 1: Write Feishu Bot plugin**

Write `src/feishu_plugin.py`:
```python
"""Polaris Feishu Bot Plugin.

Integrates with the existing FeishuBot project at /Users/kang/Code/FeishuBot.
Copy or symlink this file into FeishuBot/plugins/polaris_plugin.py.
"""

from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager

sessions: dict[str, MemoryManager] = {}


class PolarisPlugin:
    """Feishu Bot plugin for Polaris agent."""

    def __init__(self):
        self.name = "polaris"
        self.description = "Polaris 个人效率助手"
        self.commands = []  # Natural language, no specific commands

    def get_or_create_memory(self, session_id: str) -> MemoryManager:
        if session_id not in sessions:
            sessions[session_id] = MemoryManager(window_size=10)
        return sessions[session_id]

    async def handle_message(self, content: str, user_id: str, **kwargs) -> str:
        """Handle an incoming message from Feishu. Returns response string."""
        if not content.strip():
            return "你好！我是 Polaris，请告诉我你需要什么帮助？"

        memory = self.get_or_create_memory(user_id)
        agent = get_agent()

        memory.add_message(HumanMessage(content=content))
        state = AgentState(
            messages=memory.get_history(),
            intent="",
            user_profile=memory.get_profile(),
            tool_results={},
            final_response="",
            needs_clarification=False,
            pending_action=None,
        )

        try:
            result = agent.invoke(state)
            response = result.get("final_response", "抱歉，处理出错了。")
        except Exception as e:
            response = f"抱歉，出了点问题：{str(e)}"

        memory.add_message(AIMessage(content=response))
        return response
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/kang/Code/AgentPlan && python -c "from src.feishu_plugin import PolarisPlugin; p = PolarisPlugin(); print(p.name)"`
Expected: `polaris`

- [ ] **Step 3: Commit**

```bash
cd /Users/kang/Code/AgentPlan && git add src/feishu_plugin.py && git commit -m "feat: Feishu Bot plugin for Polaris integration"
```

---

### Task 15: E2E Integration & README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write integration smoke test**

Write `tests/test_e2e.py`:
```python
"""End-to-end smoke test — verifies the full graph runs without errors."""
from langchain_core.messages import HumanMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


def test_e2e_daily_planning():
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "final_response" in result
    assert isinstance(result["final_response"], str)


def test_e2e_quick_capture():
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="记一下：今天讨论了LangGraph方案")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "final_response" in result


def test_e2e_knowledge_search():
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="上次RBAC讨论了什么")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "final_response" in result
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/kang/Code/AgentPlan && pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 3: Write README.md**

```markdown
# Polaris — 个人效率 AI Agent

基于 LangGraph 的个人效率 AI Agent，支持日程管理、会前准备、知识检索、快速记录和管理操作。

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 启动 Chainlit Web UI
chainlit run src/chainlit_app.py

# 运行测试
pytest tests/ -v
```

## 架构

- **LangGraph** 状态机驱动 Agent 路由
- **Chainlit** Web 聊天界面
- **ChromaDB** 向量存储笔记索引
- **Google Calendar API** 真实日历集成

## 项目结构

见设计文档 `docs/superpowers/specs/2026-04-29-polaris-agent-design.md`
```

- [ ] **Step 4: Final commit**

```bash
cd /Users/kang/Code/AgentPlan && git add tests/test_e2e.py README.md && git commit -m "feat: E2E tests and README"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Covered By |
|---|---|
| Product overview / boundary | Task 1 (scaffold, seed data) |
| 3-layer architecture | Tasks 3-8 (tool layer), 9-12 (agent core), 13-14 (entry layer) |
| AgentState | Task 2 |
| Router + conditional edges | Task 9 |
| 5 Skill subgraphs | Tasks 10-11 |
| Confirm Node | Task 12 |
| Summarize Node | Task 12 |
| GoogleCalendarTool (CRUD) | Task 7 |
| NoteTool (CRUD + archive) | Task 5 |
| TodoTool (CRUD) | Task 4 |
| RAGSearchTool | Task 6 |
| Memory | Task 8 |
| Chainlit Web UI | Task 13 |
| Feishu Bot plugin | Task 14 |
| Data storage (JSON, Markdown, ChromaDB) | Tasks 1, 3, 6 |
| Multi-Agent | Deferred (not in MVP plan, per spec) |

### 2. Placeholder Scan

No TBD, TODO, "implement later", or vague references found. Every step has concrete code.

### 3. Type Consistency

- `AgentState` fields consistent across all tasks (`messages`, `intent`, `tool_results`, `final_response`, `needs_clarification`, `pending_action`)
- Tool names match spec: `calendar`, `todo`, `notes`, `rag_search`
- `MemoryManager` API consistent between Task 8 and Tasks 13-14
- Intent labels consistent: `daily_planning`, `meeting_prep`, `knowledge_search`, `quick_capture`, `manage`, `clarify`
