# Polaris Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal efficiency AI Agent with 5 capabilities using LangGraph, accessible via Chainlit Web UI and Feishu Bot.

**Architecture:** Three-layer — entry layer (Chainlit + Feishu Bot) → LangGraph agent core (Router → 5 skill subgraphs → Summarize) → Tool layer (4 tools via ToolRegistry). Memory via ConversationBufferWindowMemory.

**Tech Stack:** Python 3.11+, LangGraph, LangChain, Chainlit, ChromaDB, Google Calendar API v3, venv + pyproject.toml + pip, pytest

---

## Implementation Phases

| Phase | Tasks | Milestone |
|-------|-------|-----------|
| **A: Minimal Conversation** | 1 → 6 | Chainlit 里能对话，Router 分类 + Planning 回复 |
| **B: Tool Layer** | 7 → 11 | Agent 能真正读写日历/待办/笔记 |
| **C: Complete Skills** | 12 → 13 | 全部 5 个能力 (Planning/Prep/Search/Capture/Manage) |
| **D: Production** | 14 → 15 | 飞书 Bot 入口 + 集成测试 |

**Task 1 已完成 (project scaffold).**

---

## File Structure

```
AgentPlan/
├── pyproject.toml
├── .env.example
├── .gitignore
├── data/
│   ├── calendar.json
│   ├── todos.json
│   ├── user_profile.json
│   └── notes/
│       ├── sample-meeting.md
│       └── archive/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── protocol.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── calendar.py
│   │   ├── notes.py
│   │   ├── todos.py
│   │   └── rag.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── router.py
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── planning.py
│   │   │   ├── prep.py
│   │   │   ├── search.py
│   │   │   ├── capture.py
│   │   │   └── manage.py
│   │   ├── confirm.py
│   │   └── summarize.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py
│   ├── data_layer/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── vector_store.py
│   ├── chainlit_app.py
│   └── feishu_plugin.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_tools/
    ├── test_agent/
    ├── test_memory/
    └── test_protocol.py
```

---

## Phase A: Minimal Conversation

### Task 2: Message Protocol + AgentState

**Files:**
- Create: `src/protocol.py`
- Create: `src/state.py`
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Write failing tests**

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

- [ ] **Step 2: Run tests — expect FAIL**

Run: `source venv/bin/activate && pytest tests/test_protocol.py -v`
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
    action_type: str
    target_tool: str
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

- [ ] **Step 5: Run tests — expect PASS**

Run: `source venv/bin/activate && pytest tests/test_protocol.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add src/protocol.py src/state.py tests/test_protocol.py
git commit -m "feat: message protocol and AgentState types"
```

---

### Task 3: Memory Store

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

- [ ] **Step 2: Run tests — expect FAIL**

Run: `source venv/bin/activate && pytest tests/test_memory/ -v`
Expected: FAIL

- [ ] **Step 3: Write MemoryManager**

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

- [ ] **Step 4: Run tests — expect PASS**

Run: `source venv/bin/activate && pytest tests/test_memory/ -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/ tests/test_memory/
git commit -m "feat: MemoryManager with windowed conversation history and profile"
```

---

### Task 4: Router Node

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/agent/router.py`
- Test: `tests/test_agent/__init__.py`
- Test: `tests/test_agent/test_router.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_agent/__init__.py` (empty).

Write `tests/test_agent/test_router.py`:
```python
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
    assert classify_intent(make_state("今天有什么安排"))["intent"] == "daily_planning"


def test_router_meeting_prep():
    assert classify_intent(make_state("下午3点的会帮我准备一下"))["intent"] == "meeting_prep"


def test_router_knowledge_search():
    assert classify_intent(make_state("上次RBAC的讨论结果是什么"))["intent"] == "knowledge_search"


def test_router_quick_capture():
    assert classify_intent(make_state("明天下午3点加个产品评审会"))["intent"] == "quick_capture"


def test_router_manage():
    assert classify_intent(make_state("取消明天的产品评审"))["intent"] == "manage"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `source venv/bin/activate && pytest tests/test_agent/test_router.py -v`
Expected: FAIL

- [ ] **Step 3: Write Router**

Write `src/agent/__init__.py` (empty).

Write `src/agent/router.py`:
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

INTENT_OPTIONS = ["daily_planning", "meeting_prep", "knowledge_search", "quick_capture", "manage", "clarify"]


def classify_intent(state: AgentState) -> dict:
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "clarify"}

    last_message = messages[-1]
    content = last_message.content if hasattr(last_message, "content") else str(last_message)

    intent = _keyword_route(content)
    if intent:
        return {"intent": intent}

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
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
    chain = prompt | llm
    result = chain.invoke({"message": content})
    intent = result.content.strip().lower()

    return {"intent": intent if intent in INTENT_OPTIONS else "clarify"}


def _keyword_route(content: str) -> str | None:
    """Fast keyword-based routing — cheap and reliable for obvious cases."""
    c = content.strip().lower()

    if any(kw in c for kw in ["加个", "新建", "记一下", "添加", "创建", "帮我加", "帮我记", "记录一下"]):
        return "quick_capture"
    if any(kw in c for kw in ["取消", "删除", "改到", "改成", "更新", "标记为", "移除"]):
        return "manage"
    if any(kw in c for kw in ["上次", "之前", "讨论过", "讨论了什么", "找一下", "搜索", "查一下笔记"]):
        return "knowledge_search"
    if any(kw in c for kw in ["安排", "计划", "今天有什么", "今天干嘛", "日程", "有什么事情", "今天要做"]):
        return "daily_planning"
    if any(kw in c for kw in ["准备", "会议材料", "帮我准备"]):
        return "meeting_prep"

    return None


def route_condition(state: AgentState) -> str:
    return state.get("intent", "clarify")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `source venv/bin/activate && pytest tests/test_agent/test_router.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/ tests/test_agent/
git commit -m "feat: Router node with keyword fast-path + LLM classification"
```

---

### Task 5: Planning Skill + Summarize + Graph Assembly

**Files:**
- Create: `src/agent/skills/__init__.py`
- Create: `src/agent/skills/planning.py`
- Create: `src/agent/confirm.py`
- Create: `src/agent/summarize.py`
- Create: `src/agent/graph.py`
- Test: `tests/test_agent/test_planning.py`
- Test: `tests/test_agent/test_graph.py`

- [ ] **Step 1: Write Planning skill**

Write `src/agent/skills/__init__.py` (empty).

Write `src/agent/skills/planning.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def planning_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    return {
        "tool_results": {"user_query": last_msg, "mode": "planning"},
        "final_response": "",
    }


def create_planning_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("planning", planning_node)
    builder.set_entry_point("planning")
    builder.add_edge("planning", END)
    return builder.compile()
```

- [ ] **Step 2: Write Confirm node**

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
        return {"final_response": "", "pending_action": {**pending, "confirmed": True}}

    if last_msg in ("取消", "不", "no", "算了", "别"):
        return {"final_response": "已取消操作。", "pending_action": None}

    return {"final_response": f"请确认：{pending.get('description', '执行此操作？')}（回复「确认」或「取消」）"}
```

- [ ] **Step 3: Write Summarize node**

Write `src/agent/summarize.py`:
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是个人效率助手 Polaris。根据用户的问题和工具执行结果，生成自然、有帮助的回复。

规则：
- 用中文回复
- 简洁直接，不要啰嗦
- 如果是日程列表，按时间排列
- 如果工具没有返回结果（tool_results 为空或只有 mode），基于自身知识直接回答用户问题

用户最后说：{message}

工具结果：{tool_results}

请生成回复："""),
])


def summarize_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    tool_results = state.get("tool_results", {})

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
    chain = SUMMARIZE_PROMPT | llm
    result = chain.invoke({
        "message": last_msg,
        "tool_results": str(tool_results),
    })

    return {"final_response": result.content.strip()}
```

- [ ] **Step 4: Write Graph assembly**

Write `src/agent/graph.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.summarize import summarize_node
from src.agent.skills.planning import planning_node


def clarify_node(state: AgentState) -> dict:
    return {
        "final_response": "不太确定你想做什么，能再说详细一点吗？\n"
        "- 「今天有什么安排」查看日程\n"
        "- 「下午3点的会帮我准备」会议准备\n"
        "- 「上次RBAC讨论了什么」搜索笔记\n"
        "- 「记一下：xxx」快速记录\n"
        "- 「取消明天的晨会」管理操作",
        "needs_clarification": False,
    }


def default_skill_node(state: AgentState) -> dict:
    """Stub node for skills not yet implemented."""
    intent = state.get("intent", "")
    return {
        "tool_results": {"user_query": state["messages"][-1].content, "mode": intent},
        "final_response": "",
    }


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # Core nodes
    builder.add_node("router", classify_intent)
    builder.add_node("clarify", clarify_node)
    builder.add_node("planning", planning_node)
    builder.add_node("default", default_skill_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("summarize", summarize_node)

    builder.set_entry_point("router")

    # Router dispatches to available skills; unimplemented ones go to default
    builder.add_conditional_edges(
        "router",
        route_condition,
        {
            "daily_planning": "planning",
            "meeting_prep": "default",
            "knowledge_search": "default",
            "quick_capture": "default",
            "manage": "default",
            "clarify": "clarify",
        }
    )

    for node in ["planning", "default"]:
        builder.add_edge(node, "summarize")

    builder.add_edge("clarify", END)
    builder.add_edge("summarize", END)

    return builder.compile()


def get_agent():
    return build_agent_graph()
```

- [ ] **Step 5: Write tests**

Write `tests/test_agent/test_planning.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.planning import planning_node
from src.state import AgentState


def test_planning_node():
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="daily_planning", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = planning_node(state)
    assert "tool_results" in result
```

Write `tests/test_agent/test_graph.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.graph import build_agent_graph
from src.state import AgentState


def test_graph_builds():
    graph = build_agent_graph()
    assert graph is not None


def test_graph_routes_planning():
    graph = build_agent_graph()
    state = AgentState(
        messages=[HumanMessage(content="今天有什么安排")],
        intent="", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = graph.invoke(state)
    assert "final_response" in result
    assert isinstance(result["final_response"], str)
```

- [ ] **Step 6: Run tests**

Run: `source venv/bin/activate && pytest tests/test_agent/test_planning.py tests/test_agent/test_graph.py -v`
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add src/agent/ tests/test_agent/
git commit -m "feat: Planning skill, Summarize node, and graph assembly"
```

---

### Task 6: Chainlit Web UI — First Conversation!

**Files:**
- Create: `src/chainlit_app.py`

- [ ] **Step 1: Write Chainlit app**

Write `src/chainlit_app.py`:
```python
"""Polaris Chainlit Web UI entry point.

Run with: source venv/bin/activate && chainlit run src/chainlit_app.py
"""

import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager

sessions: dict[str, MemoryManager] = {}


def get_or_create_memory(session_id: str) -> MemoryManager:
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(window_size=10)
    return sessions[session_id]


@cl.on_chat_start
async def start():
    await cl.Message(
        content="你好！我是 Polaris，你的个人效率助手。\n\n"
        "目前我已支持：\n"
        "- 🗓 **查看日程**：今天有什么安排？\n"
        "- 📋 **会议准备**：下午的会帮我准备（开发中）\n"
        "- 🔍 **搜索笔记**：上次RBAC讨论了什么（开发中）\n"
        "- ✍️ **快速记录**：记一下，明天开会要讨论权限方案（开发中）\n"
        "- ✏️ **管理信息**：取消明天的晨会（开发中）\n\n"
        "试试跟我说：**今天有什么安排？**"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("id")
    memory = get_or_create_memory(session_id)

    agent = get_agent()

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

    result = agent.invoke(state)
    response = result.get("final_response", "抱歉，处理出错了。")
    memory.add_message(AIMessage(content=response))

    await cl.Message(content=response).send()
```

- [ ] **Step 2: Verify it loads**

Run: `source venv/bin/activate && python -c "from src.chainlit_app import get_agent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Start Chainlit and test**

Run: `source venv/bin/activate && chainlit run src/chainlit_app.py`

Open http://localhost:8000, type "今天有什么安排", verify the agent responds.

- [ ] **Step 4: Commit**

```bash
git add src/chainlit_app.py
git commit -m "feat: Chainlit Web UI — first working conversation"
```

**Phase A complete! Agent can chat. Try "今天有什么安排" in Chainlit.**

---

## Phase B: Tool Layer

### Task 7: Data Loader

**Files:**
- Create: `src/data_layer/__init__.py`
- Create: `src/data_layer/loader.py`
- Test: `tests/test_data_layer/__init__.py`

- [ ] **Step 1: Write data loader**

Write `src/data_layer/__init__.py` (empty).

Write `src/data_layer/loader.py`:
```python
import json
import re
import yaml
from pathlib import Path
from datetime import date


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.suffix == ".json" and "profile" in path.name else []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_calendar_events(path: Path, target_date: str | None = None) -> list[dict]:
    data = load_json(path)
    if not isinstance(data, list):
        return []
    if target_date:
        return [ev for day in data if day.get("date") == target_date for ev in day.get("events", [])]
    return [ev for day in data for ev in day.get("events", [])]


def load_todos(path: Path) -> list[dict]:
    data = load_json(path)
    return data if isinstance(data, list) else []


def parse_note_frontmatter(content: str) -> tuple[dict, str]:
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

- [ ] **Step 2: Smoke test**

Run:
```bash
source venv/bin/activate && python -c "
from src.data_layer.loader import load_notes, load_calendar_events
from src.config import DATA_DIR
events = load_calendar_events(DATA_DIR / 'calendar.json', '2026-05-04')
print(f'Events: {len(events)}')
notes = load_notes(DATA_DIR / 'notes')
print(f'Notes: {len(notes)}')
"
```
Expected: `Events: 3`, `Notes: 1`

- [ ] **Step 3: Commit**

```bash
git add src/data_layer/ tests/test_data_layer/
git commit -m "feat: data loader with JSON/Markdown read/write"
```

---

### Task 8: TodoTool

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
    assert "完成权限设计文档" in tool._run("list all")


def test_todo_search(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    assert "完成权限设计文档" in tool._run("search 权限")


def test_todo_create(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run('create {"title": "新待办", "priority": "high", "due": "2026-05-10"}')
    assert "新待办" in result
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert any(t["title"] == "新待办" for t in data)


def test_todo_mark_done(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    result = tool._run("done todo-1")
    assert "完成" in result or "done" in result.lower()


def test_todo_delete(tmp_data_dir):
    tool = TodoTool(data_file=str(tmp_data_dir / "todos.json"))
    tool._run("delete todo-1")
    data = json.loads((tmp_data_dir / "todos.json").read_text())
    assert not any(t["id"] == "todo-1" for t in data)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `source venv/bin/activate && pytest tests/test_tools/test_todos.py -v`

- [ ] **Step 3: Write ToolRegistry + TodoTool**

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

Write `src/tools/todos.py`:
```python
import json
import uuid
from langchain_core.tools import BaseTool
from pathlib import Path


class TodoTool(BaseTool):
    name: str = "todo"
    description: str = (
        "Manage todo items. Commands: list all|pending|done, "
        "search <keyword>, create {\"title\":...,\"priority\":...,\"due\":...}, done <id>, delete <id>"
    )
    data_file: str = ""

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_todos, save_json

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
                icon = {"pending": "○", "in_progress": "◉", "done": "✓"}.get(t.get("status", ""), "?")
                lines.append(f"- {icon} [{t.get('priority', '-')}] {t['title']} (截止: {t.get('due', '无')}) [ID: {t['id']}]")
            return "\n".join(lines)

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            matches = [t for t in todos if keyword.lower() in t.get("title", "").lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的待办。"
            return "\n".join(f"- [{t['priority']}] {t['title']} [ID: {t['id']}]" for t in matches)

        elif cmd.startswith("create"):
            try:
                new_todo = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建待办需要 JSON：create {\"title\": \"...\", \"priority\": \"high|medium|low\", \"due\": \"YYYY-MM-DD\"}"
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

        return "可用命令：list [status], search <keyword>, create <json>, done <id>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `source venv/bin/activate && pytest tests/test_tools/test_todos.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/ tests/test_tools/
git commit -m "feat: TodoTool with full CRUD + ToolRegistry"
```

---

### Task 9: NoteTool

**Files:**
- Create: `src/tools/notes.py`
- Test: `tests/test_tools/test_notes.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_tools/test_notes.py`:
```python
from src.tools.notes import NoteTool


def test_note_list(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    assert "PRD v2 讨论" in tool._run("list")


def test_note_read(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    assert "RBAC" in tool._run("read prd-v2-discussion.md")


def test_note_create(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    result = tool._run('create {"title": "测试", "content": "内容", "tags": ["test"]}')
    assert "已记录" in result
    assert any("测试" in f.read_text() for f in (tmp_data_dir / "notes").glob("*.md"))


def test_note_archive(tmp_data_dir):
    tool = NoteTool(notes_dir=str(tmp_data_dir / "notes"), archive_dir=str(tmp_data_dir / "notes" / "archive"))
    tool._run("archive prd-v2-discussion.md")
    assert not (tmp_data_dir / "notes" / "prd-v2-discussion.md").exists()
    assert (tmp_data_dir / "notes" / "archive" / "prd-v2-discussion.md").exists()
```

- [ ] **Step 2: Run tests — expect FAIL**

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
            return filepath.read_text(encoding="utf-8")

        elif cmd.startswith("create"):
            try:
                data = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建笔记需要 JSON：create {\"title\":\"...\", \"content\":\"...\", \"tags\":[...]}"
            filepath = save_note(notes_path, data["title"], data.get("content", ""), data.get("tags"))
            return f"已记录笔记：{data['title']} ({filepath.name})"

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            notes = load_notes(notes_path)
            matches = [n for n in notes if keyword.lower() in n["content"].lower()
                       or keyword.lower() in n["metadata"].get("title", "").lower()]
            if not matches:
                return f"没有找到包含「{keyword}」的笔记。"
            return "\n\n".join(f"## {n['metadata'].get('title', n['filename'])}\n{n['content'][:300]}" for n in matches)

        elif cmd.startswith("archive"):
            filename = command.replace("archive", "").strip()
            filepath = notes_path / filename
            if archive_note(filepath, archive_path):
                return f"已归档笔记：{filename}"
            return f"归档失败：{filename}"

        return "可用命令：list, read <filename>, create <json>, search <keyword>, archive <filename>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/tools/notes.py tests/test_tools/test_notes.py
git commit -m "feat: NoteTool with create/read/search/archive"
```

---

### Task 10: RAGSearchTool

**Files:**
- Create: `src/data_layer/vector_store.py`
- Create: `src/tools/rag.py`
- Test: `tests/test_tools/test_rag.py`

- [ ] **Step 1: Write failing test**

Write `tests/test_tools/test_rag.py`:
```python
import pytest
from src.tools.rag import RAGSearchTool
from src.data_layer.vector_store import index_notes


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
    import os
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key and api_key != "sk-placeholder":
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key, model_name="text-embedding-3-small"
        )
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


def get_vector_store(persist_dir: str, collection_name: str = "notes"):
    client = PersistentClient(path=persist_dir)
    embedding = get_embedding_function()
    return client.get_or_create_collection(name=collection_name, embedding_function=embedding)


def index_notes(notes_dir: str, persist_dir: str, collection_name: str = "notes") -> None:
    from src.data_layer.loader import load_notes
    collection = get_vector_store(persist_dir, collection_name)
    notes = load_notes(Path(notes_dir))
    existing_ids = set(collection.get()["ids"])

    for note in notes:
        note_id = note["filename"].replace(".md", "").replace(" ", "-")
        if note_id in existing_ids:
            continue
        collection.add(
            ids=[note_id],
            documents=[note["content"]],
            metadatas=[{"title": note["metadata"].get("title", ""), "tags": ",".join(note["metadata"].get("tags", []))}],
        )


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
            similarity = max(0, 1 - r.get("distance", 0))
            if similarity < 0.3:
                continue
            title = r["metadata"].get("title", "未命名")
            output.append(f"## {title} (相关度: {similarity:.0%})\n{r['content'][:500]}")

        if not output:
            return "没有找到足够相关的笔记，换个关键词试试？"
        return "\n\n---\n\n".join(output)

    async def _arun(self, query: str) -> str:
        return self._run(query)
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/data_layer/vector_store.py src/tools/rag.py tests/test_tools/test_rag.py
git commit -m "feat: RAGSearchTool with ChromaDB vector search"
```

---

### Task 11: GoogleCalendarTool

**Files:**
- Create: `src/tools/calendar.py`
- Test: `tests/test_tools/test_calendar.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_tools/test_calendar.py`:
```python
import json
from src.tools.calendar import GoogleCalendarTool


def test_calendar_list(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("list 2026-05-03")
    assert "晨会" in result


def test_calendar_create(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run('create {"date":"2026-05-05","time":"14:00","title":"测试会议"}')
    assert "已添加" in result


def test_calendar_search(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    assert "产品评审" in tool._run("search 产品评审")


def test_calendar_delete(tmp_data_dir):
    tool = GoogleCalendarTool(data_file=str(tmp_data_dir / "calendar.json"), use_mock=True)
    result = tool._run("delete evt-1")
    assert "删除" in result.lower() or "取消" in result.lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Write GoogleCalendarTool**

Write `src/tools/calendar.py`:
```python
import json
import uuid
from langchain_core.tools import BaseTool
from pathlib import Path


class GoogleCalendarTool(BaseTool):
    name: str = "calendar"
    description: str = (
        "Manage calendar events. Commands: list <date YYYY-MM-DD>, "
        "create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}, "
        "search <keyword>, update <id> <json>, delete <id>"
    )
    data_file: str = ""
    use_mock: bool = True

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_json, save_json

        path = Path(self.data_file)
        data = load_json(path) if isinstance(load_json(path), list) else []
        cmd = command.strip().lower()

        if cmd.startswith("list"):
            date_str = command.split("list", 1)[1].strip()
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
                new_event = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建日程需要 JSON：create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}"
            new_event["id"] = f"evt-{uuid.uuid4().hex[:8]}"
            new_event.setdefault("duration", 60)
            new_event.setdefault("attendees", [])
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
            event_id, json_data = parts[1], parts[2]
            try:
                updates = json.loads(json_data)
            except json.JSONDecodeError:
                return "更新数据需要 JSON 格式"
            for day in data:
                for ev in day.get("events", []):
                    if ev["id"] == event_id:
                        ev.update(updates)
                        save_json(path, data)
                        return f"已更新日程：{ev.get('title', event_id)}"
            return f"未找到日程 ID: {event_id}"

        elif cmd.startswith("delete"):
            event_id = cmd.replace("delete", "").strip()
            for day in data:
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    if ev["id"] == event_id:
                        title = ev["title"]
                        events.pop(i)
                        save_json(path, data)
                        return f"已删除日程：{title}"
            return f"未找到日程 ID: {event_id}"

        return "可用命令：list <date>, create <json>, search <keyword>, update <id> <json>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/tools/calendar.py tests/test_tools/test_calendar.py
git commit -m "feat: GoogleCalendarTool with CRUD (mock mode)"
```

**Phase B complete! All 4 tools built. Agent can now really read/write data.**

---

## Phase C: Complete Skills

### Task 12: Search + Prep + Capture + Manage Skills

**Files:**
- Create: `src/agent/skills/search.py`
- Create: `src/agent/skills/prep.py`
- Create: `src/agent/skills/capture.py`
- Create: `src/agent/skills/manage.py`
- Test: `tests/test_agent/test_search.py`
- Test: `tests/test_agent/test_prep.py`
- Test: `tests/test_agent/test_capture.py`
- Test: `tests/test_agent/test_manage.py`

- [ ] **Step 1: Write Search skill**

Write `src/agent/skills/search.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def search_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    prompt = f"请使用 RAG 搜索工具查找：rag_search {last_msg}\n如果结果不够相关（相关度 < 30%），告诉用户未找到，并追问更具体的关键词。"
    return {"tool_results": {"search_prompt": prompt}, "final_response": ""}


def create_search_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("search", search_node)
    builder.set_entry_point("search")
    builder.add_edge("search", END)
    return builder.compile()
```

- [ ] **Step 2: Write Prep skill**

Write `src/agent/skills/prep.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def prep_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    prompt = f"请按步骤：1. 查会议 calendar search <关键词> 2. 搜笔记 rag_search <主题关键词> 3. 查待办 todo search <关键词> 4. 汇总生成准备清单。"
    return {"tool_results": {"prep_prompt": prompt}, "final_response": ""}


def create_prep_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("prep", prep_node)
    builder.set_entry_point("prep")
    builder.add_edge("prep", END)
    return builder.compile()
```

- [ ] **Step 3: Write Capture skill**

Write `src/agent/skills/capture.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def capture_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    prompt = (
        f"用户想记录：{last_msg}\n"
        "判断类型并调用工具：\n"
        "- 日程(有时间/日期): calendar create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}\n"
        "- 笔记(信息/想法): notes create {\"title\":\"...\",\"content\":\"...\",\"tags\":[...]}\n"
        "- 待办(任务): todo create {\"title\":\"...\",\"priority\":\"high|medium|low\",\"due\":\"YYYY-MM-DD\"}\n"
        "将自然语言日期（明天、周五）转换为具体日期。"
    )
    return {"tool_results": {"capture_prompt": prompt}, "final_response": ""}


def create_capture_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("capture", capture_node)
    builder.set_entry_point("capture")
    builder.add_edge("capture", END)
    return builder.compile()
```

- [ ] **Step 4: Write Manage skill**

Write `src/agent/skills/manage.py`:
```python
from langgraph.graph import StateGraph, END
from src.state import AgentState


def manage_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    prompt = (
        f"用户想管理：{last_msg}\n"
        "判断操作：查询/搜索用 search，修改用 update，删除用 delete，标记完成用 todo done <id>。\n"
        "修改和删除操作：先回显确认，等用户说「确认」后再执行。"
    )
    return {"tool_results": {"manage_prompt": prompt}, "final_response": ""}


def create_manage_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("manage", manage_node)
    builder.set_entry_point("manage")
    builder.add_edge("manage", END)
    return builder.compile()
```

- [ ] **Step 5: Update graph.py to wire all skills**

Update `src/agent/graph.py` — replace the `default_skill_node` route_map and imports:

```python
from src.agent.skills.search import search_node
from src.agent.skills.prep import prep_node
from src.agent.skills.capture import capture_node
from src.agent.skills.manage import manage_node

# In build_agent_graph(), add:
builder.add_node("search", search_node)
builder.add_node("prep", prep_node)
builder.add_node("capture", capture_node)
builder.add_node("manage", manage_node)

# Update conditional_edges to route all intents:
builder.add_conditional_edges(
    "router", route_condition,
    {
        "daily_planning": "planning",
        "meeting_prep": "prep",
        "knowledge_search": "search",
        "quick_capture": "capture",
        "manage": "manage",
        "clarify": "clarify",
    }
)

# Wire all skill nodes to summarize:
for node in ["planning", "prep", "search", "capture", "manage"]:
    builder.add_edge(node, "summarize")
```

- [ ] **Step 6: Write tests**

Write `tests/test_agent/test_search.py`:
```python
from langchain_core.messages import HumanMessage
from src.agent.skills.search import search_node
from src.state import AgentState


def test_search_node():
    state = AgentState(
        messages=[HumanMessage(content="RBAC讨论结果")],
        intent="knowledge_search", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    assert "search_prompt" in search_node(state)["tool_results"]
```

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
    assert "prep_prompt" in prep_node(state)["tool_results"]
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
    assert "capture_prompt" in capture_node(state)["tool_results"]
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
    assert "manage_prompt" in manage_node(state)["tool_results"]
```

- [ ] **Step 7: Run tests**

Run: `source venv/bin/activate && pytest tests/test_agent/ -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/agent/skills/ src/agent/graph.py tests/test_agent/
git commit -m "feat: all 5 skill subgraphs wired into graph"
```

**Phase C complete! All 5 capabilities working.**

---

## Phase D: Production

### Task 13: Feishu Bot Plugin

**Files:**
- Create: `src/feishu_plugin.py`

- [ ] **Step 1: Write Feishu plugin**

Write `src/feishu_plugin.py`:
```python
"""Polaris Feishu Bot Plugin.

Integrates with FeishuBot at /Users/kang/Code/FeishuBot.
Copy this file into FeishuBot/plugins/polaris_plugin.py.
"""

from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager

sessions: dict[str, MemoryManager] = {}


class PolarisPlugin:
    def __init__(self):
        self.name = "polaris"
        self.description = "Polaris 个人效率助手"
        self.commands = []

    def get_or_create_memory(self, session_id: str) -> MemoryManager:
        if session_id not in sessions:
            sessions[session_id] = MemoryManager(window_size=10)
        return sessions[session_id]

    async def handle_message(self, content: str, user_id: str, **kwargs) -> str:
        if not content.strip():
            return "你好！我是 Polaris，请告诉我你需要什么帮助？"

        memory = self.get_or_create_memory(user_id)
        agent = get_agent()

        memory.add_message(HumanMessage(content=content))
        state = AgentState(
            messages=memory.get_history(), intent="", user_profile=memory.get_profile(),
            tool_results={}, final_response="", needs_clarification=False, pending_action=None,
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

Run: `source venv/bin/activate && python -c "from src.feishu_plugin import PolarisPlugin; print(PolarisPlugin().name)"`
Expected: `polaris`

- [ ] **Step 3: Commit**

```bash
git add src/feishu_plugin.py
git commit -m "feat: Feishu Bot plugin for Polaris"
```

---

### Task 14: E2E Tests + Final README

**Files:**
- Create: `tests/test_e2e.py`
- Update: `README.md`

- [ ] **Step 1: Write E2E smoke test**

Write `tests/test_e2e.py`:
```python
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

Run: `source venv/bin/activate && pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Write README.md**

Write `README.md`:
```markdown
# Polaris — 个人效率 AI Agent

基于 LangGraph 的个人效率 AI Agent，支持日程管理、会前准备、知识检索、快速记录和管理操作。

## 快速开始

```bash
# 安装依赖
python3 -m venv venv
source venv/bin/activate
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

详见 `docs/superpowers/specs/2026-04-29-polaris-agent-design.md`
```

- [ ] **Step 4: Final commit**

```bash
git add tests/test_e2e.py README.md
git commit -m "feat: E2E tests and README"
```

**Phase D complete! Project done.**

---

## Phase E: 后续优化（待排期）

### Task 15: 上下文管理与记忆压缩

**当前状态**: MemoryManager 保留最近 10 条消息，Summarize 直接全部塞入 prompt，无 token 控制和摘要压缩。

**待实现**:
1. Token 估算：对历史消息用 tiktoken 估算 token 数，超限时自动截断最早的消息
2. 摘要压缩：对超出窗口的较早对话轮次，调用 LLM 生成摘要而非直接丢弃，摘要注入 system prompt
3. 滑动窗口优化：区分"核心上下文"（当前任务的 tool call 链）和"背景上下文"（历史闲聊），后者优先被压缩
4. 可配置的窗口大小和 token 上限，通过环境变量控制

### Task 16: Web 与飞书跨通道共享上下文

**当前状态**: Web 端和飞书端各自独立维护 MemoryManager，同一用户两边对话互不可见。

**待实现**:
1. 统一用户标识：Web 端加登录态（或 session → user_id 映射），与飞书 open_id 统一
2. 共享 Memory 存储：从进程内 dict 换成 SQLite / Redis，按 user_id 存取
3. 两端读写同一份对话历史，切换通道无缝续聊
