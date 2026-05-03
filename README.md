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

## 开发须知：事件系统与模块开发

### EventBus 发布订阅机制

通过 `src/events.py` 提供的事件总线实现模块间零耦合通信。框架层发布事件，各模块订阅处理。

```python
from src.events import event_bus

# 订阅
event_bus.subscribe("cleanup:now", my_cleanup_handler)

# 发布
event_bus.publish("config:reload")
```

**订阅在模块的 `__init__.py` 中进行**，模块被 import 时自动完成订阅，无需手动调用初始化函数。

### 支持的事件

| 事件 | 发布者 | 发布时机 | 订阅者 |
|------|--------|----------|--------|
| `config:reload` | `src/config.py` | `/reload` 命令后 | executor（清 LLM 缓存） |
| `cleanup:now` | `src/session/commands.py` | `/cleanup` 命令 | 各 tools 模块清理过期数据 |
| `cleanup:cron` | `src/server.py` | 每天凌晨 3:00 | 各 tools 模块清理过期数据 |

### 新增事件的约定

1. 事件名格式：`<域>:<动作>`，如 `cleanup:now`、`config:reload`
2. 发布者不需要知道订阅者是谁
3. 订阅者在 `__init__.py` 中调用 `event_bus.subscribe(...)`，在模块顶层执行
4. 处理器函数签名 `def handler(**kwargs)`，便于未来扩展参数

### 新增一个工具的步骤

以新增"天气工具"为例：

1. 创建 `src/tools/weather/tool.py`，实现 `WeatherTool(BaseTool)` + `create_default()`
2. 创建 `src/tools/weather/__init__.py`：
   ```python
   from .tool import WeatherTool, create_default
   ```
3. 如需清理旧数据，在 `__init__.py` 中订阅事件：
   ```python
   from .tool import WeatherTool, create_default
   from src.events import event_bus

   def _on_cleanup(**kwargs):
       # 清理过期天气缓存...
       pass

   event_bus.subscribe("cleanup:now", _on_cleanup)
   event_bus.subscribe("cleanup:cron", _on_cleanup)
   ```
4. 无需修改 `server.py`、`config.py` 或任何其它文件。`ToolRegistry` 自动发现。

### 新增一个通道的步骤

1. 创建 `src/channels/wechat/client.py`，实现 `WechatChannel(ChannelPlugin)`
2. 创建 `src/channels/wechat/__init__.py`：`from .client import WechatChannel`
3. 在 `data/config.yaml` 添加配置：
   ```yaml
   channels:
     wechat:
       plugin: "src.channels.wechat"
       enabled: true
       corp_id: ""
       corp_secret: ""
   ```
4. 无需修改任何 Python 框架代码。YAML 驱动动态加载。

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

# 配置
cp data/config.local.yaml.example data/config.local.yaml
# 编辑 config.local.yaml，至少填入：
#   llm.api_key: sk-xxx
#   llm.base_url: https://api.openai.com/v1
#   llm.model: gpt-4o
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
| `/cleanup` | 手动触发数据清理/归档 |
| `/help` | 显示帮助 |

## 技术栈

| 层面 | 技术 |
|------|------|
| Agent 框架 | LangGraph StateGraph + ReAct 循环 |
| LLM | ChatOpenAI（可替换，支持 DeepSeek 等兼容 API） |
| 工具定义 | LangChain BaseTool + Pydantic args_schema |
| 向量检索 | ChromaDB + Embedding API（OpenAI 兼容） |
| 定时调度 | APScheduler → CronScheduler（src/cron） |
| 模块通信 | EventBus 发布订阅 |
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
│   ├── server.py               # FastAPI Agent Server（不依赖具体 tools/channels）
│   ├── config.py               # YAML 配置中心（热重载），无模块级业务变量
│   ├── context.py              # contextvars 上下文传播
│   ├── events.py               # EventBus 发布订阅（框架与模块解耦）
│   ├── handler.py              # 消息处理入口
│   ├── lock.py                  # per-session 异步锁
│   ├── llm/                     # LLM Provider 抽象
│   ├── cron/                    # 通用定时调度（无关业务）
│   ├── storage/                 # 存储层抽象（DataStore + 原子写入）
│   ├── middleware/              # Auth / RateLimit 中间件
│   │
│   ├── agent/
│   │   ├── graph.py            # LangGraph 图组装
│   │   ├── executor.py         # agent_node / tool_node
│   │   ├── interceptors.py     # 工具拦截器（删除确认等）
│   │   └── state.py            # AgentState 类型定义
│   │
│   ├── session/
│   │   ├── manager.py          # 多会话管理 + 持久化
│   │   └── commands.py         # 系统命令（/cleanup 等发事件）
│   │
│   ├── channels/               # YAML 驱动加载，每个 channel 独立子目录
│   │   ├── base.py             # ChannelPlugin 基类
│   │   ├── loader.py           # YAML → 动态加载 + is_configured 检查
│   │   ├── feishu/             # 飞书（WebSocket Bot，超长消息分段）
│   │   └── qq/                 # QQ（botpy SDK）
│   │
│   ├── tools/                  # 每个 tool 独立子目录，自动发现
│   │   ├── _utils.py           # find_by_id_or_title
│   │   ├── registry.py         # ToolRegistry 单例（扫描子目录）
│   │   ├── calendar/           # 日程（关联提醒 + 清理过期）
│   │   ├── todos/              # 待办
│   │   ├── notes/              # 笔记
│   │   ├── reminder/           # 定时提醒（模型/存储/调度/推送/清理）
│   │   ├── web_search/         # 联网搜索
│   │   ├── persona/            # 人设配置
│   │   └── rag/                # RAG 语义搜索
│   │
│   └── memory/
│       ├── store.py            # 对话记忆
│       └── compressor.py       # Token 预算压缩
│
├── data/                       # 运行时数据
│   ├── config.yaml             # 全局默认配置
│   ├── config.local.yaml       # 本地敏感配置（gitignore）
│   ├── sessions/               # 会话存储
│   ├── reminders.json          # 提醒数据
│   ├── calendar.json
│   ├── todos.json
│   └── notes/
│
└── docs/                       # 设计文档
```
