# Polaris — 个人效率 AI Agent 设计文档

- **版本**: v2.0
- **日期**: 2026-04-30
- **状态**: Implemented（与当前代码一致）
- **变更**: 架构从 Router + 5 技能子图重构为 ReAct 循环，新增 Agent Server、通道插件系统、Token 预算压缩、多会话管理

---

## 一、产品概述

Polaris 是一个面向个人知识工作场景的 AI Agent，帮助用户完成**每日规划**、**会前准备**、**知识检索**、**快速记录**和**信息管理**五类任务。用户通过统一入口用自然语言交互，Agent 通过 ReAct 循环自主决定调用哪些工具完成操作。

### 核心价值

将分散的日历、笔记、待办数据整合为一个对话式入口，既是"帮你想"（规划/准备/检索）也是"帮你记"（创建/修改/清理）。从"分散在多处手动操作"变成"一句话搞定"。

### 产品边界

- 日程：增删改查
- 待办：增删改查
- 笔记：增改查（删除改为归档，避免数据丢失）
- 删除/修改操作在提示词中要求先确认再执行（确认节点待实现）
- 不做高风险外部执行、多人协作、移动端 App

---

## 二、架构设计

### 2.1 整体架构

```
通道层                Agent Server 层              LangGraph 层
──────────────────────────────────────────────────────────────
Chainlit Web ──┐    ┌──────────────────┐    ┌──────────────────┐
               ├───▶│ /chat/stream SSE │    │  command_node     │
飞书 Bot ──────┘    │ /chat            │    │  (拦截 / 命令)     │
                    │ /sessions        │    │      ↓            │
QQ/微信等 ─────┐    │ SessionManager   │───▶│  agent_node       │
(可扩展)      └───▶│ ChannelManager   │    │  (LLM+tools) ⇄    │
                    │ ToolRegistry     │    │  tool_node        │
                    └──────────────────┘    │  (工具执行)        │
                                            └──────────────────┘
```

**设计原则**: Agent 核心层通过 FastAPI Server 统一对外暴露 HTTP/SSE 接口，所有通道（Web、飞书等）作为客户端接入。同一套 LangGraph 逻辑同时服务所有通道。

### 2.2 通道层

- **Chainlit Web UI**: 通过 SSE 流式消费 Agent Server 的 `/chat/stream` 端点，支持 Token 级实时输出和思考链可视化（`cl.Step`）
- **飞书 Bot**: 复用已有 FeishuBot WebSocket 基建，同进程内直接调用 `process_message()`，不经过 HTTP
- **可扩展通道**: `ChannelPlugin` 抽象基类 + `ChannelManager` 自动发现机制，新增通道只需实现 `name`、`is_configured()`、`start()` 三个方法
- **统一消息协议**: 所有通道发送 `{message: str, session_id: str}` 到 `process_message()`，返回 `(response_text, tool_calls)`

### 2.3 Agent 核心层（LangGraph）

采用 LangGraph `StateGraph`，图结构为 `command_node → agent_node ⇄ tool_node → END`：

**AgentState（TypedDict）**:
- `messages`: 对话历史（Annotated add_messages，LangGraph 自动合并）
- `intent`: 保留字段（当前未用于路由，仅占位）
- `user_profile`: 用户偏好
- `tool_results`: 工具执行结果
- `final_response`: 最终回复（命令节点设置此字段绕过后继 LLM 调用）
- `needs_clarification`: 是否需要追问
- `pending_action`: 待确认操作（预留，确认节点使用）
- `streaming: bool`: **新增**。True 时 `agent_node` 用 `chain.stream()` 累积 AIMessageChunk 以生成 Token 级 SSE 事件；False 时直接用 `chain.invoke()`

**节点与边**:
- `command_node`: 预处理节点。识别以 `/` 开头的系统命令，调用 `handle_command()` 处理，设置 `final_response` 直接结束。非命令消息透明放行至 agent_node。
- `agent_node`: LLM 推理节点。加载全部工具（`ToolRegistry.list_tools()`），`bind_tools()` 绑定为 function calling 定义。根据 `streaming` 标志选择流式或非流式调用。流式路径用 `AIMessageChunk` 累加器合并增量 tool call 数据。
- `tool_node`: 工具执行节点。遍历 AIMessage 的 `tool_calls`，通过 `ToolRegistry` 查找并执行对应工具，返回 `ToolMessage`。
- `should_continue`: 条件边。检查最后一条消息是否有 `tool_calls`，有则回到 `tool_node`，无则结束。

**与 v1.0 Router 架构的对比**:
| v1.0 (设计) | v2.0 (实际) | 原因 |
|-------------|-------------|------|
| Router Node (LLM 分类意图) | 无 | LLM function calling 天然具备意图路由能力 |
| 5 个 Skill 子图 | agent_node 统一处理 | 子图拆分引入不必要的复杂性 |
| Confirm Node | 待实现 | 提示词中有行为准则，二次确认流程后续加 |
| Summarize Node | agent_node 内置 | LLM 在工具结果后自然生成汇总 |

### 2.4 Tool 层

统一 `BaseTool` 接口，所有工具使用 **Pydantic `args_schema`** 定义结构化参数（而非字符串命令），通过 `ToolRegistry` 单例注册和发现。

| Tool | 名称 | 数据源 | 能力 |
|------|------|--------|------|
| GoogleCalendarTool | `calendar` | 本地 JSON + Google Calendar API v3 | 增删改查，mock/真 API 双模式 |
| TodoTool | `todo` | 本地 JSON | 增删改查 |
| NoteTool | `notes` | 本地 Markdown 文件 | 增改查，归档（非真删） |
| RAGSearchTool | `rag_search` | ChromaDB 向量库 | 只读语义检索 |

**工具发现机制**: `_get_all_tools()` → `ToolRegistry.list_tools()` 动态获取全部已注册工具，system prompt 中不再硬编码工具名称。新增工具只需在 `server.py` 启动时调用一次 `registry.register()`，其余全部自动。

**工具参数结构**（以 TodoTool 为例）:
```
TodoInput(BaseModel):
  action: "list" | "search" | "create" | "done" | "delete"
  status: "active" | "all" | "pending" | "done" (可选)
  keyword: str (可选)
  title: str (可选)
  priority: "high" | "medium" | "low" (可选)
  due: str (可选, YYYY-MM-DD)
  todo_id: str (可选)
```

所有字段均有中文 `description`，LLM 通过 function calling JSON Schema 原生理解。

### 2.5 系统命令

8 个系统命令由 `command_node` 拦截，不经 LLM，不消耗 token，不残留消息记录：

| 命令 | 功能 |
|------|------|
| `/new <名称>` | 创建新会话并切换 |
| `/sessions` | 列出所有会话 |
| `/session <id\|名称>` | 切换会话（支持 ID 前缀/名称模糊匹配）|
| `/rename <名称>` | 重命名当前会话 |
| `/status` | 显示会话消息统计、Token 用量 |
| `/compact` | 手动触发上下文压缩 |
| `/reset` | 清空当前会话记忆 |
| `/reload` | 热重载 `.env` 配置 |
| `/help` | 显示帮助信息 |

---

## 三、Agent Server 与多会话

### 3.1 Agent Server

FastAPI 服务（端口 8700），统一后端入口：

- **`POST /chat`** — 非流式对话（供飞书等非实时通道使用），返回完整 `{session_id, response, tool_calls}`
- **`POST /chat/stream`** — SSE 流式对话（供 Chainlit Web UI 使用），事件类型：
  - `data: {"token": "..."}` — Token 级流式输出
  - `event: tool_call` — 工具调用开始（含名称和参数）
  - `event: tool_result` — 工具执行完成（含返回结果）
  - `event: done` — 流式结束
  - `event: error` — 错误信息
- **`GET /sessions`** — 列出所有会话
- **`POST /sessions/{id}/activate`** — 切换活跃会话

### 3.2 多会话管理

`SessionManager` 管理多个独立会话，持久化到 `data/sessions.json`：

- **Session 结构**: `{session_id, name, memory, compressor, created_at, last_active, metadata}`
- **持久化策略**: 每次交互后调用 `save()`，保存前自动运行 compressor 确保旧消息被压缩到摘要
- **恢复策略**: 从 JSON 直接重建 `_messages` 列表，绕过 `window_size` 截断
- **默认会话**: 首次运行自动创建"默认"会话
- **切换匹配**: 精确 ID → ID 前缀 → 名称模糊搜索

### 3.3 跨通道共享上下文

由于所有通道共享同一个 `SessionManager` 单例，且消息处理通过 `threading.Lock` 串行化，**不同通道之间天然共享会话上下文**。用户在 Web 上的对话切换到飞书后，飞书 Bot 看到的是同一段对话历史。

---

## 四、上下文管理

### 4.1 双层记忆模型

采用 Token 预算驱动的压缩策略（而非消息数驱动）：

- **摘要层**: LLM 生成的压缩摘要，注入 system prompt（`[对话摘要]\n{summary}`）
- **最近消息层**: Token 预算内的最近消息原样保留

### 4.2 压缩触发条件

`total_tokens = messages_tokens + summary_tokens + RESERVE_TOKENS(8000)`
当 `total_tokens > model_max_context * 0.8` 时触发压缩。

默认 `model_max_context = 200000`，触发线 = 160k tokens。

### 4.3 压缩策略

1. 从后向前扫描消息，找到 token 预算内能容纳的最近消息分界点
2. 超出部分（oldest messages）送入 LLM 合并到已有摘要
3. 安全裁剪：压缩后仍超标则逐条移出
4. Token 计数优先使用 tiktoken（cl100k_base），不可用时退化为 `len(text)//2`

### 4.4 跨轮次记忆清理

每次交互后，`memory._messages` 被重置为 `previous_messages + [HumanMessage, AIMessage]`：
- 中间的 ToolMessage 和中间 AIMessage 不保留
- 只保留用户输入 + 最终 AI 回复
- 下次 LLM 调用时只看到干净的 user/ai 对话对

---

## 五、数据存储

### 5.1 模拟数据

- `data/calendar.json`: 日历事件（mock 模式或 GCAL 同步）
- `data/notes/*.md`: 笔记文件（YAML frontmatter 做元数据）
- `data/notes/archive/`: 归档笔记
- `data/todos.json`: 待办事项
- `data/user_profile.json`: 用户偏好
- `data/sessions.json`: 会话持久化数据

### 5.2 向量存储

- ChromaDB 本地持久化（`data/chroma/`）
- 笔记内容 → 硅基流动 Embedding API → 分 collection 存储
- 通过 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` 配置
- 未配置时向量检索不可用，提示用户配置
- RAGSearchTool 只读检索

### 5.3 Memory

- `MemoryManager`: 简单的消息列表 + `window_size` 安全上限
- 非流式路径和流式路径均在交互后手动重置 `_messages`，剥离中间工具消息
- 用户偏好存入 `user_profile.json`

---

## 六、技术选型

| 层面 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph StateGraph | 状态机模型，command→agent⇄tools |
| LLM | 可替换 ChatOpenAI | 支持 DeepSeek 等兼容 API |
| 工具定义 | BaseTool + Pydantic args_schema | 结构化参数，原生 function calling |
| Embedding | 硅基流动 Embedding API（OpenAI 兼容）| 云端推理，无需 GPU |
| Vector DB | ChromaDB | 轻量本地持久化 |
| Web 服务 | FastAPI + SSE | 统一后端，流式/非流式双接口 |
| Web UI | Chainlit + httpx | SSE 客户端，思考链可视化 |
| Bot 通道 | 飞书 WebSocket（lark-oapi）| 同进程直接调用 |
| Token 计数 | tiktoken (cl100k_base) | 精确计数，回退 char/2 估算 |
| 包管理 | venv + pyproject.toml + pip | PEP 621 标准 |

---

## 七、决策记录（面试参考）

### 决策 1: 为什么选个人效率 Agent 而不是代码助手？

**选择**: 个人效率 Agent

**理由**:
1. 代码助手领域 Claude Code / Copilot 已很强，差异化空间有限
2. 个人效率 Agent 处于多源数据整合的交叉领域
3. 覆盖 LangChain 核心模块（Tool、Memory、RAG、Chain）最全面
4. 面试故事性强："连接自己的日历、笔记、待办让 Agent 主动规划"

### 决策 2: 为什么用 ReAct 循环替代 Router + 5 技能子图？

**选择**: 单一 ReAct agent_node + 全部工具绑定

**理由**:
1. LLM function calling 天然具备意图路由能力——用户说"今天有什么安排"时，LLM 自主决定调用 calendar + todo，无需 Router 层分类
2. 5 个技能子图实质上都是"调工具 → 汇总回复"，拆成 5 个子图引入了大量重复的 prompt engineering 和冗余代码
3. ReAct 模式是 LangChain 最成熟的 Agent 范式，代码更简洁，bug 面更小
4. 面试价值不减：结构化 args_schema、Token 预算压缩、双入口架构、多会话管理等话题同样有讨论深度

### 决策 3: 为什么选模拟数据 + Google Calendar 真实 API？

**选择**: 模拟 + Google Calendar 真实 API（双模式）

**理由**:
1. 全部真 API：~30% 时间耗在 OAuth、API 对接上，偏离 LangChain 学习目标
2. 全部模拟：简历缺真实集成点
3. 混合方案：Google Calendar API 成熟、文档全；其余模拟数据保证开发效率
4. 所有 Tool 通过统一接口注册，后续随时换成真实 API

### 决策 4: 为什么选 Web 聊天界面 + 飞书 Bot 双入口？

**选择**: Chainlit Web UI + 飞书 Bot

**理由**:
1. Python CLI TUI 库不成熟，开发体验差
2. Chainlit 专为 LangChain 设计，原生支持 streaming、tool call 可视化——面试 demo 效果好
3. 飞书 Bot 已有现成 WebSocket 基建
4. 双入口验证了 Agent 核心的接口解耦设计——系统设计面试的讨论点

### 决策 5: 为什么用 Pydantic args_schema 定义工具参数？

**选择**: `BaseTool.args_schema` 结构化参数

**理由**:
1. LangChain 的 `bind_tools()` 自动将 Pydantic model 转为 JSON Schema 传递给 LLM
2. 相比手动写字符串参数说明（如 "action(list/search/create/delete), date, title..."），结构化定义更精确、不发散
3. 中文 `Field(description=...)` 让 LLM 原生理解每个字段的含义
4. 新增工具时参数定义即文档，不需要同步维护 system prompt

### 决策 6: 为什么用 Token 预算驱动压缩而非消息数驱动？

**选择**: Token 预算（tiktoken 精确计数）

**理由**:
1. 短中文消息和长工具返回结果 token 量差异巨大，按消息数压缩不精确
2. 适配 200k 大上下文模型——160k 触发线远高于常见的 10-20 条消息
3. LLM 摘要层 + 最近消息层的双层架构，在保留最近完整上下文的同时持续累积摘要

### 决策 7: 为什么引入 Agent Server 统一后端？

**选择**: FastAPI 统一后端，所有通道作为客户端接入

**理由**:
1. 解耦通道与 Agent 逻辑：新增通道（QQ、微信等）只需实现客户端，不改 Agent 代码
2. 多会话天然共享：同一进程内的 SessionManager 单例，Web 和飞书共享会话上下文
3. 接口标准化：`/chat` (非流式) + `/chat/stream` (SSE) 覆盖所有通道需求
4. 面试价值：多通道架构 + 会话共享是企业级 Agent 平台的常见需求

### 决策 8: 为什么选择通道插件体系？

**选择**: `ChannelPlugin` 抽象基类 + `ChannelManager` 自动发现

**理由**:
1. 飞书 Bot 不应是硬编码的独立服务——未来可能接 QQ、微信、钉钉等
2. 每个通道实现 `name`、`is_configured()`、`start()` 三个方法即可自动注册
3. 通道配置检查放在 `is_configured()` 中（检查环境变量），未配置的通道静默跳过

---

## 八、待实现

| 事项 | 说明 |
|------|------|
| 确认节点（Confirm Node）| 删除/修改操作的二次确认流程，提示词已写"先确认再执行"但无编程实现 |
| 测试 | 工具层单元测试、Agent 图集成测试、会话管理测试均待补充 |
| Google Calendar 真实 API | 当前使用 `use_mock=True`，需配置 Service Account 切换到真 API |
| 笔记写入自动更新 RAG 索引 | NoteTool 创建/修改笔记后不会自动向量化入库 |
| Multi-Agent 协作 | 预留设计，后续迭代加入 |
