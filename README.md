# Polaris — 个人效率 AI Agent

> 你的私人 AI 秘书：管日程、记待办、搜笔记、联网查资料、看图说话、语音合成，定时提醒 + 心跳任务主动推送到飞书或 QQ。每个会话可以是不同的人——诸葛亮出谋划策，哈利波特陪你闲聊。

基于 **LangGraph + ReAct** 构建，自然语言驱动日程、待办、笔记、搜索、语音合成。支持图片理解（多模态），发送图片即可识别内容。定时提醒 + 心跳任务周期性执行自定义提示词，结果通过 YAML 配置的多通道插件推送到消息平台。

试用入口：**[demo.yankang.space](https://demo.yankang.space)**

## 功能概览

**定时提醒，主动推送。** 不只是被动问答——设个提醒，到点自动推送到你所在的渠道。支持一次性/每天/每周/每月重复，日程创建自动关联提前 15 分钟提醒，服务重启后自动恢复。

```
用户："明天上午 9 点提醒我开会"
→ 创建提醒 → SchedulerDomain 调度 → 到点推送飞书/QQ

用户："帮我建个下午 3 点的日程"
→ 创建日程 → 自动关联 14:45 的提前提醒
```

**8 个内置工具，插件化自动发现。** 每个工具独立子目录，`ToolRegistry` 启动时扫描注册，新增工具只需创建目录和实现 `create_default()` 工厂函数。

| 工具 | 能力 |
|------|------|
| calendar | 日程增删改查 + 提醒自动关联 |
| todos | 待办管理，支持优先级、截止日期 |
| notes | 笔记管理 + RAG 语义搜索（ChromaDB） |
| reminder | 定时提醒，支持暂停/恢复/周期重复 |
| web_search | 联网搜索（Tavily API） |
| persona | 会话独立人格（名称/身份/性格/称呼） |
| rag | 笔记内容语义检索 |
| voice | MiMo TTS 语音合成，支持预置音色、音频标签、自然语言风格控制 |

**多通道，插件配置驱动。** 飞书 WebSocket Bot、QQ botpy SDK——所有通道共享会话记忆。新增通道只需写实现 + YAML 配置，不动框架代码。超长消息按段落/句子边界智能分段。Admin Web UI 由 FastAPI 直接托管。

**会话独立人格。** 不同会话可以是不同角色——诸葛亮、哈利波特、或一个默认助手。人格持久化存储，切换会话即切换角色。

**消息重试与编辑。** hover 用户消息可重新生成或修改后重新触发，SSE 流式输出，前后端完整支持。

**心跳定时任务。** 可配置的间隔触发机制，读取提示词文件自动调用 LLM 处理，结果推送到绑定 channel。适合定时汇报、每日总结等场景。

**Token 预算感知的上下文压缩。** 基于 tiktoken 精确计数，超出阈值时自动摘要压缩（LLM 摘要层 + 最近消息层），重启无损恢复。

**多模态图片理解。** 支持发送图片，AI 自动识别内容并回复。飞书和 QQ 通道均支持图片消息解析。

**语音合成。** 集成 MiMo TTS，支持 8 种预置音色（中文/英文）、音频标签情绪控制、自然语言风格描述。Web 端点击播放，QQ 通道语音条发送。

## 技术架构

```
src/
  server/                    # FastAPI 服务
    app.py                   #   入口（lifespan + 中间件 + 路由挂载）
    middleware/              #   认证、速率限制、Demo 模式
    routes/                  #   API 路由（chat, sessions, config, voice 等）

  core/                      # 基础设施层
    config/                  #   YAML 配置中心 + Pydantic Schema 校验
    infra/                   #   EventBus、contextvars、per-session 锁
    observability/           #   结构化日志、Metrics 指标
    channel/                 #   ChannelPlugin 基类 + YAML 驱动 loader
    llm/                     #   LLM 协议 + OpenAI 兼容工厂
    memory/                  #   MemoryManager 消息列表容器
    storage/                 #   DataStore 协议 + JsonFileStore + 原子写入
    tools/                   #   ToolRegistry + entity_utils
    errors.py                #   统一错误体系（ToolError/ValidationError/NotFoundError）

  domains/                   # 业务领域层（DDD）
    calendar/                #   日程 CRUD + EventBus 事件
    todos/                   #   待办 CRUD + 状态过滤
    notes/                   #   笔记 CRUD + 向量索引同步
    persona/                 #   会话人格管理
    reminder/                #   提醒 CRUD + 调度委托 + 日程事件订阅
    scheduler/               #   统一任务调度（APScheduler + JSON 持久化 + 重启恢复）
    rag/                     #   向量存储 + 分块 + 文档解析
    voice/                   #   MiMo TTS + STT + WAV→silk/mp3 转换

  tools/                     # LLM 工具适配层（薄适配器，~40行/个）
    calendar/                #   调用 CalendarDomain
    todos/                   #   调用 TodoDomain
    notes/                   #   调用 NotesDomain
    reminder/                #   调用 ReminderDomain
    persona/                 #   调用 PersonaDomain
    rag/                     #   调用 RAGDomain
    voice/                   #   调用 VoiceDomain
    web_search/              #   Tavily API

  channels/                  # 通道插件（YAML 驱动 + 动态 import）
    feishu/                  #   飞书 WebSocket Bot
    qq/                      #   QQ botpy SDK（支持语音消息）

  agent/                     # LangGraph ReAct agent
  message/                   # 消息路由（统一入口：锁 + 上下文 + agent 调用）
  session/                   # 多会话管理 + 系统命令
  cron/                      # 心跳 + 每日清理
```

**依赖方向：** `server/channels/tools → domains → core`。tools 只做 LLM 协议适配，domains 拥有完整业务逻辑，core 提供基础设施。跨模块通信通过 EventBus 发布订阅。

## 开发须知

### EventBus — 模块间零耦合通信

```python
from src.core.infra.events import event_bus

event_bus.subscribe("cleanup:now", my_handler)  # 订阅
event_bus.publish("config:reload")              # 发布
```

订阅在 domain 的 `_on_startup` 中注册，`app:startup` 事件触发。事件名格式 `<domain>:<entity>_<action>`。

| 事件 | 发布者 | 订阅者 |
|------|--------|--------|
| `app:startup` | server 启动 | 各 domain 初始化、scheduler 恢复任务 |
| `config:reload` | /reload 命令 | LLM 缓存清理、channel 重启 |
| `cleanup:now` | /cleanup 命令 | calendar、todo、reminder 清理过期数据 |
| `cleanup:cron` | cron 每天 3:00 | 同上 |
| `calendar:event_*` | CalendarDomain | ReminderDomain 自动关联提醒 |
| `notes:note_*` | NotesDomain | RAGDomain 自动向量索引 |
| `scheduler:job_*` | SchedulerDomain | — |
| `reminder:reminder_*` | ReminderDomain | — |

完整事件列表见 [EventBus 事件参考](docs/eventbus.md)。

### 新增工具

1. 创建 `src/tools/weather/tool.py`，实现 `WeatherTool(BaseTool)` + `create_default()`
2. 创建 `src/tools/weather/__init__.py`（一行 re-export）
3. 完成。`ToolRegistry` 自动发现，不需改任何其他文件。

### 新增通道

1. 创建 `src/channels/wechat/`，实现 `WechatChannel(ChannelPlugin)`
2. `data/config.yaml` 加配置：
   ```yaml
   channels:
     wechat:
       plugin: "src.channels.wechat"
       enabled: true
   ```
3. 完成。不碰框架代码。

## 快速开始

- Python ≥ 3.12
- OpenAI 兼容 API Key

```bash
cd Polaris
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# 配置
cp data/config.local.yaml.example data/config.local.yaml
# 编辑 config.local.yaml，至少填入 llm 下的 api_key

# 启动
cd admin && npm install && npm run build && cd ..
python run.py
# 访问 http://localhost:8700
```

### 多实例部署

同一服务器上运行多个 Polaris 实例（如自用 + 公开试用），用 `--home` 指定独立数据目录：

```bash
# 自用实例（默认端口 8700）
python run.py

# 公开试用实例（端口 8800，独立数据，每IP每日50条消息）
mkdir -p /opt/polaris-demo/data
# 编辑 /opt/polaris-demo/data/config.local.yaml（API key 等）
python run.py --home /opt/polaris-demo --port 8800 --demo 50
```

不同实例的数据（会话、提醒、日程）完全隔离。

## 系统命令

| 命令 | 功能 |
|------|------|
| `/new <名称>` | 创建新会话 |
| `/sessions` | 查看所有会话 |
| `/session <id\|名称>` | 切换会话 |
| `/rename <名称>` | 重命名当前会话 |
| `/status` | 会话状态（消息数、Token 用量） |
| `/compact` | 手动触发上下文压缩 |
| `/reset` | 重置当前会话记忆 |
| `/reload` | 热重载配置（无需重启） |
| `/cleanup` | 手动清理过期数据 |
| `/help` | 显示帮助 |

## 技术栈

LangGraph + ReAct / ChatOpenAI / FastAPI + SSE / Vue 3 + Vite / APScheduler / ChromaDB / tiktoken / contextvars / Pydantic / MiMo TTS
