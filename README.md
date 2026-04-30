# Polaris — 个人效率 AI Agent

基于 **LangGraph** 的个人效率 AI Agent，你可以随时随地让它帮你记日程、记待办、记笔记，也可随时问它你的日程，帮你规划一天，它就是你的私人秘书。

> 一句话介绍：一个基于 LangGraph 的个人效率 AI Agent（Polaris）。它通过 ReAct 工具执行循环，将日历、待办、笔记的增删改查统一为一个自然语言对话入口——用户一句话即可完成日程规划、会议准备、知识检索或快速记录。Agent 采用 Command → Agent Node ⇄ Tool Node 的三层架构，支持 Chainlit Web UI 和飞书 Bot 双入口，具备 Token 预算感知的上下文压缩、多会话管理、SSE 流式输出和可插拔通道系统。

## 项目亮点

**架构设计**
- **统一 Agent Server**：FastAPI 服务端，`/chat`（非流式）和 `/chat/stream`（SSE 流式）两种接口，同一套图逻辑同时服务 Web 和飞书
- **ReAct 循环**：Agent Node（LLM + 工具绑定）⇄ Tool Node，LLM 自主决策何时调用工具，无需 Router 中间层
- **可插拔通道**：`ChannelPlugin` 抽象基类 + `ChannelManager` 自动发现，新增通道只需写一个插件类

**工具系统**
- **结构化 Schema**：4 个工具（calendar、todo、notes、rag_search）全部使用 Pydantic `args_schema`，利用 LLM 原生 function calling
- **工具自动发现**：`ToolRegistry.list_tools()` 动态获取，新增工具只需注册一次，无需改任何其他代码
- **单点注册**：`server.py` 启动时一次性注册所有工具，全局生效

**上下文管理**
- **Token 预算驱动压缩**：基于消息 token 数（tiktoken）而非消息数量判断是否压缩，适配 不同上下文窗口模型
- **双层记忆**：LLM 摘要层 + 最近消息层，压缩阈值 = 模型最大上下文 × 80%
- **重启无损恢复**：保存前走 compressor 压缩，确保摘要 + 最近消息完整持久化

**多会话**
- 支持创建、切换、重命名会话，可持久化到
- 切换支持 ID 前缀匹配和名称模糊匹配
- 默认会话自动创建，开箱即用
- 多通道共享会话，多设备间无缝切换

**流式体验**
- Web 端 SSE Token 级流式输出，实时展示 LLM 生成过程
- 思考链可视化：`💭 思考推理` Step → `🔧 调用工具` Step（含输入参数）→ 工具结果 → 最终回复

**安全与稳定性**
- 全局消息锁保证并发安全
- LLM 调用失败自动回滚内存，不污染对话历史
- 工具消息不在跨轮次记忆中残留，节省 token
- 配置热重载（`/reload`），无需重启

## 架构

```
通道层               Agent Server 层               LangGraph 层
──────────────────────────────────────────────────────────────
Chainlit Web ──┐   ┌──────────────────┐     ┌──────────────────┐
               ├──▶│ /chat/stream SSE │     │  command_node    │
飞书 Bot ──────┘   │ /chat            │     │  (拦截 / 命令)    │
                   │ /sessions        │     │      ↓           │
                   │ SessionManager   │────▶│  agent_node      │
                   │ (多会话持久化)    │     │  (LLM+tools)⇄    │
                   │ ToolRegistry     │     │  tool_node       │
                   │ ChannelManager   │     │  (工具执行)       │
                   └──────────────────┘     └──────────────────┘
```

## 快速开始

### 环境要求

- Python ≥ 3.12 且 < 3.14
- OpenAI 兼容 API Key（支持 DeepSeek 等）

### 安装

```bash
# 克隆项目
cd Polaris

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入：
#   OPENAI_API_KEY=sk-xxx
#   OPENAI_BASE_URL=https://api.openai.com/v1  （或其他兼容 API）
#   LLM_MODEL=gpt-4o
```

### 启动

```bash
# 一键启动（Agent Server + 所有通道）
python run.py
# Server 启动在 http://localhost:8700
```

### 启动 Web UI

```bash
# 另开终端
source venv/bin/activate
chainlit run src/chainlit_app.py
# Web UI 启动在 http://localhost:8000
```

### 启用飞书 Bot

在 `.env` 中配置：

```env
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
```

启动后飞书通道自动注册。

## 项目结构

```
Polaris/
├── pyproject.toml              # 项目配置（PEP 621 + venv + pip）
├── run.py                      # 一键启动入口
├── .env.example                # 环境变量模板
│
├── src/
│   ├── server.py               # FastAPI Agent Server（统一入口）
│   ├── config.py               # 配置中心（热重载支持）
│   ├── state.py                # AgentState 类型定义
│   ├── protocol.py             # 消息协议
│   ├── session_manager.py      # 多会话管理 + 持久化
│   ├── system_commands.py      # 系统命令（/sessions、/reset 等）
│   │
│   ├── agent/
│   │   ├── graph.py            # LangGraph 图组装（command → agent ⇄ tools）
│   │   └── executor.py         # agent_node / tool_node / should_continue
│   │
│   ├── tools/
│   │   ├── registry.py         # ToolRegistry 单例
│   │   ├── calendar.py         # GoogleCalendarTool（mock + 真 API 双模式）
│   │   ├── todos.py            # TodoTool
│   │   ├── notes.py            # NoteTool
│   │   └── rag.py              # RAGSearchTool（ChromaDB 语义搜索）
│   │
│   ├── memory/
│   │   ├── store.py            # MemoryManager（对话记忆）
│   │   └── compressor.py       # ConversationCompressor（Token 预算压缩）
│   │
│   ├── channels/
│   │   ├── __init__.py         # ChannelPlugin 基类 + ChannelManager
│   │   └── feishu.py           # 飞书通道插件
│   │
│   ├── data_layer/
│   │   ├── loader.py           # JSON/Markdown 数据读写
│   │   └── vector_store.py     # ChromaDB 向量存储
│   │
│   ├── chainlit_app.py         # Chainlit Web UI（SSE 客户端）
│   └── feishu_bot.py           # 飞书 WebSocket Bot
│
├── data/                       # 种子数据
│   ├── calendar.json
│   ├── todos.json
│   ├── user_profile.json
│   └── notes/
│
└── docs/superpowers/           # 设计文档
    ├── specs/                  # 3 份设计规范
    └── plans/                  # 实施计划
```

## 能力矩阵

| 场景 | 触发示例 | 调用工具 |
|------|----------|----------|
| 每日规划 | "今天有什么安排" | calendar + todo |
| 会议准备 | "下午3点的会帮我准备" | calendar + rag_search |
| 知识检索 | "上次 RBAC 讨论了什么" | rag_search |
| 快速记录 | "记一下，明天下午开会" | calendar / notes / todo |
| 管理操作 | "取消明天的晨会" | calendar / todo |
| 普通对话 | "你好" | 无（纯 LLM） |

## 系统命令

| 命令 | 功能 |
|------|------|
| `/new <名称>` | 创建新会话 |
| `/sessions` | 查看所有会话 |
| `/session <id\|名称>` | 切换会话 |
| `/rename <名称>` | 重命名当前会话 |
| `/status` | 查看会话状态（消息数、Token 用量） |
| `/compact` | 手动触发上下文压缩 |
| `/reset` | 重置当前会话记忆 |
| `/reload` | 热重载配置（无需重启） |
| `/help` | 显示帮助 |

## 技术栈

| 层面 | 技术 |
|------|------|
| Agent 框架 | LangGraph StateGraph + ReAct 循环 |
| LLM | ChatOpenAI（可替换，支持 DeepSeek 等兼容 API） |
| 工具定义 | LangChain BaseTool + Pydantic args_schema |
| 向量检索 | ChromaDB + sentence-transformers |
| Web 服务 | FastAPI + SSE |
| Web UI | Chainlit + httpx 流式客户端 |
| Bot 通道 | 飞书 WebSocket（lark-oapi） |
| Token 计数 | tiktoken |
| 包管理 | venv + pyproject.toml + pip（PEP 621） |
