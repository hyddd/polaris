# Polaris — 个人效率 AI Agent

> 你的私人 AI 秘书：一句话管日程、记待办、查笔记、搜资料，定时提醒主动推送到你的飞书或 QQ。每个会话可以是不同的人——诸葛亮帮你出谋划策，哈利波特陪你聊天解闷。

基于 **LangGraph** 构建的个人效率助手，支持自然语言交互完成日程规划、待办管理、知识检索。内置定时提醒系统，可关联日程自动创建提醒，并通过飞书/QQ 渠道主动推送通知。支持会话独立人格，不同会话拥有不同的身份、性格和称呼。

## 核心亮点

### 1. 定时提醒 + 渠道主动推送

不只是被动问答——设个提醒，到点自动推送到你所在的渠道。

```
用户："明天上午 9 点提醒我开会"
→ 创建提醒 → APScheduler 调度 → 到点推送飞书/QQ 消息

用户："帮我建个下午 3 点的日程"
→ 创建日程 → 自动关联 14:45 的提前提醒 → 到点推送
```

- 支持一次性 / 每天 / 每周 / 每月重复提醒
- 日程创建自动关联提前 15 分钟提醒，日程修改/删除同步更新
- 服务重启后提醒自动恢复，过期提醒补触发
- 提醒推送通过 contextvars 精确路由到创建渠道

### 2. 7 个内置工具，按文件自动发现

| 工具 | 能力 |
|------|------|
| **calendar** | 日程增删改查，支持搜索、批量操作 |
| **todo** | 待办管理，支持优先级、截止日期 |
| **notes** | 笔记管理 + RAG 语义搜索（ChromaDB） |
| **reminder** | 定时提醒，支持暂停/恢复/重复 |
| **web_search** | 联网搜索（Tavily API），查天气、新闻、事实 |
| **persona** | 会话独立人格配置（名称/身份/性格/称呼用户） |
| **rag_search** | 笔记语义检索 |

新增工具只需在 `src/tools/` 下创建文件，实现 `create_default()` 工厂函数，**无需修改任何其他代码**。

### 3. 多通道接入 + 消息主动推送

| 通道 | 接入方式 | 主动推送 |
|------|----------|----------|
| Admin UI | SSE 流式 + REST | 写入 session |
| 飞书 | WebSocket Bot | 支持，超长消息自动分段 |
| QQ | botpy SDK | 支持 |

所有通道共享会话和记忆，多设备无缝切换。通过 `contextvars` 统一管理 channel/session/user 上下文，消息处理期间 context 不变，并发安全。

### 4. 消息重试与编辑

ChatGPT 级别的对话体验：

- **重新生成**：hover 用户消息，点击重试按钮，用相同输入重新调用
- **编辑消息**：修改已发送内容后重新触发，后续对话基于编辑后的内容继续
- 前后端完整支持，SSE 流式输出

### 5. 智能上下文管理

- **Token 预算驱动压缩**：基于 tiktoken 精确计算，而非粗暴截断消息数
- **双层记忆**：LLM 摘要层 + 最近消息层，压缩阈值 = 模型最大上下文 × 80%
- **重启无损恢复**：持久化前压缩，摘要 + 最近消息完整保存
- **工具执行结构化日志**：记录工具名、参数、耗时、结果，慢查询（>5s）自动告警

### 6. 会话独立人格

每个会话拥有独立的人设配置，不同会话可以是不同的"人"：

```
会话 A："你是诸葛亮，叫我主公"  → 沉稳睿智的军师风格
会话 B："你是哈利波特"          → 魔法世界的少年语气
会话 C：不设置                  → 默认助手
```

支持配置：名称、称呼用户、身份设定、性格特点、时区、自由备注。人格持久化存储，重启不丢失。切换会话 = 切换人格，多角色共存互不干扰。

### 7. 安全与稳定性

- **Chat API 访问控制**：`CHAT_TOKEN` 可选认证，保护对话隐私
- **会话锁防并发**：per-session 锁 + contextvars，消息处理期间 context 不变
- **LLM 调用失败自动回滚**：不污染对话历史
- **Config 热重载**：`/reload` 切换模型时自动清除 LLM 缓存
- **原子文件写入**：备份 + 临时文件 + rename，写入失败自动恢复

## 架构

```
通道层               Agent Server 层               LangGraph 层
──────────────────────────────────────────────────────────────
Admin UI ──────┐   ┌──────────────────┐     ┌──────────────────┐
               ├──▶│ /chat/stream SSE │     │  command_node    │
飞书 Bot ──────┤   │ /chat            │     │  (拦截 / 命令)    │
               │   │ /sessions        │     │      ↓           │
QQ Bot ────────┘   │ SessionManager   │────▶│  agent_node      │
                   │ ChannelManager   │     │  (LLM+tools)⇄    │
                   │ ReminderScheduler│     │  tool_node       │
                   │ ToolRegistry     │     │  (工具执行)       │
                   │ ContextVars      │     └──────────────────┘
                   └──────────────────┘
```

## 快速开始

### 环境要求

- Python ≥ 3.12 且 < 3.14
- OpenAI 兼容 API Key（支持 DeepSeek 等）

### 安装

```bash
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
#   OPENAI_BASE_URL=https://api.openai.com/v1
#   LLM_MODEL=gpt-4o
```

### 启动

```bash
# 构建前端（首次）
cd admin && npm install && npm run build && cd ..

# 启动服务
python run.py
# 访问 http://localhost:8700 进入管理后台
```

### 启用通道

```env
# 飞书
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx

# QQ
QQ_BOT_APPID=1903763025
QQ_BOT_SECRET=xxxxxxxx

# Web 搜索（可选）
SEARCH_API_KEY=tvly-xxxxxxxx

# Chat API 认证（可选）
CHAT_TOKEN=your-secret-token
```

## 能力矩阵

| 场景 | 触发示例 | 调用工具 |
|------|----------|----------|
| 每日规划 | "今天有什么安排" | calendar + todo |
| 会议准备 | "下午3点的会帮我准备" | calendar + rag_search |
| 知识检索 | "上次 RBAC 讨论了什么" | rag_search |
| 快速记录 | "记一下，明天下午开会" | calendar / notes / todo |
| 设置提醒 | "5分钟后提醒我喝水" | reminder |
| 联网搜索 | "今天天气怎么样" | web_search |
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
| 向量检索 | ChromaDB + Embedding API（OpenAI 兼容） |
| 定时调度 | APScheduler（BackgroundScheduler） |
| Web 服务 | FastAPI + SSE |
| 管理后台 | Vue 3 + Vite + Element Plus + Pinia |
| Bot 通道 | 飞书 WebSocket（lark-oapi）、QQ（botpy） |
| 上下文传播 | contextvars（线程隔离，并发安全） |
| Token 计数 | tiktoken |
| 包管理 | venv + pyproject.toml + pip（PEP 621） |

## 项目结构

```
Polaris/
├── pyproject.toml              # 项目配置
├── run.py                      # 一键启动入口
├── .env.example                # 环境变量模板
│
├── admin/                      # Vue 3 管理后台
│   ├── src/
│   │   ├── views/              # 页面（Chat/Session/Config/Data）
│   │   ├── components/         # 组件（ChatMessage/ToolStep 等）
│   │   └── stores/             # Pinia 状态管理
│   └── dist/                   # 构建产物
│
├── src/
│   ├── server.py               # FastAPI Agent Server
│   ├── config.py               # 配置中心（热重载）
│   ├── context.py              # contextvars 上下文传播
│   │
│   ├── agent/
│   │   ├── graph.py            # LangGraph 图组装
│   │   ├── executor.py         # agent_node / tool_node
│   │   ├── interceptors.py     # 工具拦截器（删除确认等）
│   │   └── state.py            # AgentState 类型定义
│   │
│   ├── session/
│   │   ├── manager.py          # 多会话管理 + 持久化
│   │   └── commands.py         # 系统命令
│   │
│   ├── channels/
│   │   ├── __init__.py         # ChannelPlugin + ChannelManager
│   │   ├── feishu.py           # 飞书（超长消息自动分段）
│   │   └── qq.py               # QQ（主动消息推送）
│   │
│   ├── tools/                  # 工具自动发现
│   │   ├── registry.py         # ToolRegistry 单例
│   │   ├── calendar.py         # 日程（关联提醒）
│   │   ├── todos.py            # 待办
│   │   ├── notes.py            # 笔记
│   │   ├── reminder.py         # 定时提醒
│   │   ├── web_search.py       # 联网搜索
│   │   ├── persona.py          # 人设配置
│   │   └── rag.py              # RAG 语义搜索
│   │
│   ├── reminders/
│   │   ├── models.py           # Reminder 数据模型
│   │   ├── store.py            # JSON 持久化存储
│   │   ├── scheduler.py        # APScheduler 调度器
│   │   └── handlers.py         # 提醒触发 → 渠道推送
│   │
│   ├── memory/
│   │   ├── store.py            # 对话记忆
│   │   └── compressor.py       # Token 预算压缩
│   │
│   └── data_layer/
│       ├── loader.py           # JSON/Markdown 读写（原子写入）
│       └── vector_store.py     # ChromaDB 向量存储
│
├── data/                       # 运行时数据
│   ├── sessions/               # 会话存储
│   ├── reminders.json          # 提醒数据
│   ├── calendar.json
│   ├── todos.json
│   └── notes/
│
└── docs/                       # 设计文档
```
