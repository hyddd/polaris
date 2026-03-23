# Polaris — 个人效率 AI Agent

基于 **LangGraph** 的个人效率 AI Agent，通过 **ReAct 工具执行循环**将日历、待办、笔记的增删改查统一为一个自然语言对话入口。用户一句话即可完成日程规划、会议准备、知识检索或快速记录。

## 一句话介绍

> 我构建了一个基于 LangGraph 的个人效率 AI Agent（Polaris）。它通过 ReAct 工具执行循环，将日历、待办、笔记的增删改查统一为一个自然语言对话入口——用户一句话即可完成日程规划、会议准备、知识检索或快速记录。Agent 采用 Router → Agent Node ⇄ Tool Node 的三层架构，支持 Chainlit Web UI 和飞书 Bot 双入口，目前已完整实现 5 种意图识别、4 个 Tool 的 CRUD 闭环、滑动窗口对话记忆和 Human-in-the-loop 安全确认机制。

## 架构

```
入口层              Agent 核心层                   Tool 层
──────────────────────────────────────────────────────────
Chainlit Web UI ─┐   ┌──────────────────┐     ┌──────────────┐
                 ├──▶│ Router (意图分类) │     │ CalendarTool │
飞书 Bot ────────┘   │   ↓              │     │ NoteTool     │
                     │ Agent Node       │────▶│ TodoTool     │
                     │ (LLM+bind_tools) │     │ RAGSearchTool│
                     │   ⇄              │     └──────────────┘
                     │ Tool Node        │
                     │   ↓              │
                     │ END (final answer)│
                     └──────────────────┘
```

## 快速开始

```bash
# 环境准备
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 配置
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 启动 Chainlit Web UI
chainlit run src/chainlit_app.py

# 启动飞书 Bot（可选，需配置 FEISHU_APP_ID / FEISHU_APP_SECRET）
python -m src.feishu_bot

# 运行测试
pytest tests/ -v
```

## 能力矩阵

| 意图 | 触发示例 | 调用工具 |
|------|----------|----------|
| 🗓 每日规划 | "今天有什么安排" | calendar + todo |
| 📋 会议准备 | "下午3点的会帮我准备" | calendar + rag_search + todo |
| 🔍 知识检索 | "上次RBAC讨论了什么" | rag_search |
| ✍️ 快速记录 | "记一下，明天下午开会" | calendar / notes / todo |
| ✏️ 管理操作 | "取消明天的晨会" | calendar / todo |
| 💬 普通对话 | "你好" / "你是谁" | 无（纯 LLM） |

## 技术栈

- **Agent 框架**：LangGraph 状态机 + ReAct 循环
- **LLM**：ChatOpenAI 可替换（默认 gpt-4o）
- **向量检索**：ChromaDB + text-embedding-3-small / sentence-transformers
- **Web UI**：Chainlit
- **Bot 通道**：飞书 WebSocket（lark-oapi）
- **包管理**：venv + pyproject.toml + pip

## 项目结构

```
AgentPlan/
├── pyproject.toml          # 项目配置
├── src/
│   ├── config.py           # 配置中心
│   ├── state.py            # AgentState 类型
│   ├── protocol.py         # 消息协议
│   ├── agent/
│   │   ├── graph.py        # LangGraph 图组装
│   │   ├── router.py       # 意图分类器
│   │   ├── executor.py     # ReAct Agent + Tool 执行
│   │   ├── confirm.py      # 人机确认节点
│   │   └── skills/         # 技能子图（预留）
│   ├── tools/
│   │   ├── registry.py     # ToolRegistry
│   │   ├── calendar.py     # GoogleCalendarTool
│   │   ├── notes.py        # NoteTool
│   │   ├── todos.py        # TodoTool
│   │   └── rag.py          # RAGSearchTool
│   ├── memory/store.py     # 对话记忆
│   ├── data_layer/         # JSON/Markdown/ChromaDB
│   ├── chainlit_app.py     # Chainlit 入口
│   └── feishu_bot.py       # 飞书 Bot 入口
├── data/                   # 种子数据
├── tests/                  # 43 个测试
└── docs/superpowers/       # 设计文档 & 开发计划
```

## 决策记录

| # | 决策 | 理由 |
|---|------|------|
| 1 | 选择个人效率 Agent 方向 | 差异化大，覆盖 LangChain 模块全面 |
| 2 | 五合一 Router 模式 | 学 Router/Planner 核心概念 |
| 3 | 模拟数据 + Google Calendar 真 API | 学习效率 & 真实集成点兼顾 |
| 4 | Web UI + 飞书 Bot 双入口 | 验证 Agent 核接口解耦；Python TUI 不成熟 |
| 5 | LangGraph 而非经典 ReAct | Router 天然映射状态图；面试加分 |
| 6 | 日程待办完整 CRUD | Human-in-the-loop 确认 → 企业级安全模式 |
| 7 | 预留 Multi-Agent 扩展 | LangGraph 子图嵌套天然支持 |
