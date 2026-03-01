# Polaris — 个人效率 AI Agent 设计文档

- **版本**: v1.1
- **日期**: 2026-04-29
- **状态**: Draft

---

## 一、产品概述

Polaris 是一个面向个人知识工作场景的 AI Agent，帮助用户完成**每日规划**、**会前准备**、**知识检索**、**快速记录**和**信息管理**五类任务。用户通过统一入口用自然语言交互，Agent 自动识别意图、调度工具完成操作。

### 核心价值

将分散的日历、笔记、待办数据整合为一个对话式入口，既是"帮你想"（规划/准备/检索）也是"帮你记"（创建/修改/清理）。从"分散在多处手动操作"变成"一句话搞定"。

### 产品边界

- 日程：增删改查
- 待办：增删改查
- 笔记：增改查（删除改为归档，避免数据丢失）
- 删除/修改操作有确认机制（Agent 找到目标 → 回显 → 用户确认 → 才执行）
- 不做高风险外部执行、多人协作、移动端 App

---

## 二、架构设计

### 2.1 三层架构

```
入口层        Agent 核心层              Tool 层
──────────────────────────────────────────────────
Chainlit ─┐   ┌─────────────┐     ┌──────────────────┐
          ├──▶│ Router Node │     │ GoogleCalendarTool│
飞书 Bot ─┘   │    (LLM)    │     │ NoteTool          │
              │  条件边分发  │     │ TodoTool          │
              └──────┬──────┘     │ RAGSearchTool     │
                     │            └────────┬─────────┘
              ┌──────▼──────┐             │
              │ Skill 子图  │◀────────────┘
              │ - Planning  │
              │ - Prep      │
              │ - Search    │
              │ - Capture   │
              │ - Manage    │
              └──────┬──────┘
                     ▼
              ┌────────────┐
              │  Memory    │
              │  跨轮共享  │
              └────────────┘
```

### 2.2 入口层

- **Chainlit Web UI**: 本地/桌面聊天界面，原生支持 LangChain streaming、tool call 可视化
- **飞书 Bot**: 复用已有 FeishuBot 基建（WebSocket + 插件架构），新增插件将消息路由到 Agent 核心
- **统一消息协议**: 两个入口都发送 `{message: str, session_id: str}` 到 Agent，Agent 返回 `{response: str, steps: list}` — 入口层只负责展示

### 2.3 Agent 核心层（LangGraph）

采用 LangGraph `StateGraph`，状态机驱动：

**AgentState（TypedDict）**:
- `messages`: 对话历史（Annotated add_messages）
- `intent`: Router 分类结果
- `user_profile`: 用户偏好（Memory 注入）
- `tool_results`: Tool 执行结果
- `final_response`: 最终回复
- `needs_clarification`: 是否需要追问
- `pending_action`: 待确认操作（删除/修改时先存这里）

**节点与边**:
- `Router Node`: LLM 分类用户意图到 {daily_planning, meeting_prep, knowledge_search, quick_capture, manage, clarify}
- 条件边: 根据 intent 分发到对应 Skill 子图或 Clarify 节点
- `Clarify Node`: 信息不足时生成追问
- 五个 Skill 子图: 各自内部的 Tool 调用链
- `Confirm Node`: 删除/修改操作先回显，等待用户确认再执行
- `Summarize Node`: 汇总工具结果，生成最终回复

### 2.4 Tool 层

统一 `BaseTool` 接口，通过 `ToolRegistry` 注册：

| Tool | 数据源 | 能力 |
|------|--------|------|
| GoogleCalendarTool | Google Calendar API v3 | 增删改查，Service Account 认证 |
| NoteTool | 本地 Markdown 文件 | 增改查，归档（非真删） |
| TodoTool | 本地 JSON | 增删改查 |
| RAGSearchTool | ChromaDB 向量库 | 只读语义检索，NoteTool 写操作时自动更新索引 |

---

## 三、Skill 子图设计

### 3.1 Daily Planning（每日规划）

```
用户: "今天有什么安排？"
  → Router: daily_planning
  → GoogleCalendarTool.list_events(today)
  → TodoTool.list(status=pending)
  → 冲突检测: 事件时间 vs 待办截止
  → 生成: 按时间线排列的计划 + 提醒
```

### 3.2 Meeting Prep（会前准备）

```
用户: "下午3点的会帮我准备"
  → Router: meeting_prep
  → GoogleCalendarTool: 查会议详情（标题、参与者、时间）
  → RAGSearchTool: 搜索相关笔记
  → TodoTool: 查关联待办
  → 生成: 会议背景摘要 + 准备清单
```

### 3.3 Knowledge Search（知识检索）

```
用户: "上次关于RBAC的讨论结果是什么"
  → Router: knowledge_search
  → RAGSearchTool: 向量检索相关笔记
  → 相关性判断 (< 阈值则追问用户)
  → 生成: 定位原文 + 摘要
```

### 3.4 Quick Capture（快速记录）

```
用户: "明天下午3点加个产品评审会"
  → Router: quick_capture
  → LLM 提取结构化信息（date, time, title, attendees）
  → GoogleCalendarTool.create_event(...)
  → "已添加：明天 15:00 产品评审"

用户: "记一下：RBAC方案选了角色继承模型"
  → Router: quick_capture
  → LLM 提取（title, content, tags）
  → NoteTool.create(...)
  → RAGSearchTool 自动更新向量索引
  → "已记录笔记：RBAC方案-角色继承模型"

用户: "加个待办：周五前完成权限设计文档，高优先级"
  → Router: quick_capture
  → LLM 提取（title, due, priority）
  → TodoTool.create(...)
  → "已添加待办：完成权限设计文档，截止周五"
```

### 3.5 Manage（管理操作）

```
用户: "取消明天下午的产品评审"
  → Router: manage
  → GoogleCalendarTool.search("产品评审", tomorrow)
  → 找到匹配事件 → 进入 Confirm Node
  → "找到：明天 15:00 产品评审，确认取消？"
  → 用户确认 → GoogleCalendarTool.delete(event_id)
  → "已取消"

用户: "把产品评审改到周五上午10点"
  → Router: manage
  → GoogleCalendarTool.search("产品评审")
  → 找到匹配事件 → 进入 Confirm Node
  → "将「产品评审」从明天 15:00 改到周五 10:00？"
  → 用户确认 → GoogleCalendarTool.update(event_id, new_time)
  → "已更新"

用户: "权限设计文档的待办改成已完成"
  → Router: manage
  → TodoTool.search("权限设计文档")
  → TodoTool.update(todo_id, status="done")
  → "已更新待办状态"
```

### 3.6 Confirm Node（确认机制）

所有 write/update/delete 操作需要用户确认时进入此节点：
1. Agent 找到目标资源
2. 生成确认提示，显示将执行什么操作
3. 等待用户下一条消息
4. 用户说"确认"/"取消" → 执行或放弃

---

## 四、数据存储

### 4.1 模拟数据

- `data/calendar.json`: 日历事件（受 Google Calendar 同步覆盖）
- `data/notes/*.md`: 笔记文件（YAML frontmatter 做元数据）
- `data/notes/archive/`: 归档笔记
- `data/todos.json`: 待办事项
- `data/user_profile.json`: 用户偏好

### 4.2 向量存储

- ChromaDB 本地持久化
- 笔记内容 → Embedding → 分 collection 存储
- NoteTool 写操作触发增量索引更新（只更新变更的笔记，不全量重建）

### 4.3 Memory

- LangChain `ConversationBufferWindowMemory`（最近 K 轮）
- 用户偏好存入 `user_profile.json`

---

## 五、技术选型

| 层面 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph | LangChain 主推的 Agent 方案，状态机模型 |
| LLM | 可替换（默认 OpenAI/DeepSeek） | 通过 LangChain ChatModel 抽象 |
| Embedding | text-embedding-3-small 或本地 | 笔记向量化 |
| Vector DB | ChromaDB | 轻量本地，开发体验好 |
| Web UI | Chainlit | 专为 LangChain 设计的聊天 UI |
| Bot | 复用 FeishuBot | 已有 WebSocket + 插件架构 |
| 包管理 | venv + pyproject.toml + pip | Python 虚拟环境 + PEP 621 标准项目配置 |

---

## 六、决策记录（面试参考）

### 决策 1: 为什么选个人效率 Agent 而不是代码助手？

**背景**: 用户在 KAgent 已有研究规划 Agent 设计，本次项目目的是学习 Agent 开发。

**选项**:
- A: 实现 KAgent 研究规划 Agent
- B: 另起炉灶做个人效率 Agent
- C: 做代码助手 Agent
- D: 做最小实验项目

**选择**: B — 个人效率 Agent

**理由**:
1. KAgent 已有完整设计，重复实现学习增量小
2. 代码助手领域 Claude Code / Copilot 已很强，差异化空间有限
3. 个人效率 Agent 处于多源数据整合的交叉领域，通用助手产品难以切入
4. 覆盖 LangChain 核心模块（Tool、Memory、RAG、Chain）最全面
5. 面试故事性强："连接自己的日历、笔记、待办让 Agent 主动规划"

### 决策 2: 为什么五合一（规划 + 准备 + 检索 + 记录 + 管理）而不是聚焦单一场景？

**选项**:
- 只做一个场景
- 多功能 Router 模式

**选择**: Router 模式，覆盖 5 个场景

**理由**:
1. 单一场景学不到 Router/Planner 模式，而这是 Agent 架构的核心概念
2. 不同场景覆盖 LangChain 不同模块组合（规划侧重 Tool 编排，准备侧重 Chain，检索侧重 RAG，记录侧重结构化提取，管理侧重确认流程）
3. 面试时 Router + Confirm Node 的安全设计是区别于普通 ChatBot 的关键点

### 决策 3: 为什么选模拟数据 + Google Calendar 真实 API？

**选项**:
- 全部真实 API（Google Cal + Notion + Todoist）
- 全部模拟数据
- 模拟 + 一个真实 API

**选择**: 模拟 + Google Calendar 真实 API

**理由**:
1. 全部真 API：~30% 时间耗在 OAuth、API 对接上，偏离 LangChain 学习目标
2. 全部模拟：简历缺真实集成点，面试时少了"踩坑经历"
3. 混合方案：Google Calendar API 成熟、文档全、Service Account 认证简单，1-2 小时能跑通；其余模拟数据保证开发效率
4. 所有 Tool 通过统一接口注册，后续随时换成真实 API

### 决策 4: 为什么选 Web 聊天界面 + 飞书 Bot 双入口？

**选项**:
- CLI / Web UI / 飞书 Bot / 两者结合

**选择**: Chainlit Web UI + 飞书 Bot（复用 FeishuBot 基建）

**理由**:
1. Python CLI TUI 库（Textual/Rich）不够成熟，开发体验差
2. Chainlit 专为 LangChain 设计，原生支持 streaming、tool call 可视化——面试 demo 效果好
3. 飞书 Bot 已有现成基建（WebSocket + 插件架构），加一个插件即可
4. 双入口验证了 Agent 核心的接口解耦设计——这是系统设计面试里的讨论点

### 决策 5: 为什么选 LangGraph 而不是经典 ReAct Agent？

**选项**:
- A: LangGraph 状态机
- B: 经典 create_tool_calling_agent + AgentExecutor
- C: 混合

**选择**: A — LangGraph

**理由**:
1. Router + 条件分发的场景天然是状态图，LangGraph 直接映射，代码即文档
2. LangChain 团队明确把 LangGraph 作为 Agent 主推框架，经典 ReAct Agent 趋于维护模式
3. 状态机模型对多 Agent 扩展友好（子图嵌套），后续加子 Agent 不需重构
4. 面试差异化："我用状态图建模 Agent 决策流程"比"我调了 AgentExecutor"更有讨论深度
5. 原生支持 streaming、checkpoint、human-in-the-loop

### 决策 6: 为什么日程和待办要支持完整 CRUD？

**选项**:
- 只读（信息整合）
- 读写（完整助理）

**选择**: 完整 CRUD

**理由**:
1. 产品心智：用户期望的"个人助理"应该能帮做而不只是帮看
2. LangGraph 的 Confirm Node 模式恰好展示 Human-in-the-loop 设计，这是企业级 Agent 的核心安全模式
3. Quick Capture + Manage 两个意图覆盖了 "NL → 结构化操作" 的完整链路，面试可展开聊结构化提取 + 安全确认
4. 笔记删改用归档而非真删，体现对数据安全的思考

### 决策 7: 为什么要加 Multi-Agent？

**背景**: 当前五个场景通过单个 Agent + Router 即可覆盖，Multi-Agent 非必需。

**选择**: 保留 Multi-Agent 扩展设计，后续迭代加入

**理由**:
1. 面试中 Multi-Agent 是高区分度话题
2. LangGraph 子图嵌套天然支持，不增加额外架构成本
3. 实际场景：当 Planning/Prep/Search 需要内部审查、结果交叉校验时引入协作 Agent
4. 可以作为项目的"进阶章节"，体现持续迭代

---

## 七、不在范围内

- 高风险外部执行操作（发送邮件、自动回复等）
- 多人协作 / 团队版
- 移动端原生 App
- 语音输入
- LLM Provider 深度适配（架构支持替换但不优先做）
