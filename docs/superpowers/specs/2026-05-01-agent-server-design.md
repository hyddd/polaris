# Polaris Agent Server — 统一服务层 + 会话管理 设计文档

- **版本**: v1.0
- **日期**: 2026-05-01（实际日期 2026-04-30）
- **状态**: Draft

---

## 一、设计目标

将 Polaris 从"每个通道独立进程"重构为"统一 Agent Server + 多通道接入"：

1. Agent Server 单进程，集中管理 Tool、Memory、Compressor
2. 多会话：用户可创建多个独立上下文的会话，在任意通道间自由切换
3. 多通道：飞书、Web、QQ、微信等通过 HTTP/SSE 接入，只做消息翻译
4. 私有部署，无用户认证——所有会话视为同一用户的不同上下文

---

## 二、架构

```
┌──────────────────────────────────────────────────────┐
│                  Agent Server (FastAPI)               │
│                                                      │
│  POST /chat          ─ 非流式回复（飞书/QQ/微信）       │
│  POST /chat/stream   ─ SSE 流式（Web）                 │
│  POST /sessions      ─ 创建新会话                      │
│  GET  /sessions      ─ 列出所有会话                     │
│  GET  /sessions/{id} ─ 会话详情 + 消息历史              │
│  POST /sessions/{id}/activate ─ 激活（切换）会话        │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Session  │  │  Agent   │  │     Tools        │   │
│  │ Manager  │  │  Graph   │  │ (calendar, todo,  │   │
│  │          │  │          │  │  notes, rag)      │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐
    │ 飞书 Bot │    │ Web UI  │    │   QQ    │
    │(HTTP cli)│    │(SSE cli)│    │(未来)   │
    └─────────┘    └─────────┘    └─────────┘
```

---

## 三、数据模型

### 3.1 会话 (Session)

```python
@dataclass
class Session:
    session_id: str          # 唯一标识，如 "sess_a1b2c3d4"
    name: str                # 用户可读名称，如 "工作规划"
    created_at: datetime
    last_active_at: datetime
    memory: MemoryManager    # 该会话独立的对话记忆
    compressor: ConversationCompressor  # 独立的上下文压缩器
    is_active: bool          # 是否为当前活跃会话
    metadata: dict           # {source_channel: str, message_count: int, summary: str}
```

### 3.2 会话存储

进程内 `dict[str, Session]`，重启丢失。后续可换 SQLite 持久化。

### 3.3 会话 ID 生成

`sess_` + 8 位随机 hex，如 `sess_a1b2c3d4`。

---

## 四、API 设计

### 4.1 对话 API

**POST /chat**
```
Request:
{
  "message": "今天有什么安排",
  "session_id": "sess_a1b2c3d4",   // 可选，不传则用当前活跃会话
  "channel": "feishu"               // 可选，记录来源通道
}

Response (非流式):
{
  "session_id": "sess_a1b2c3d4",
  "response": "你今天有3个会议：...",
  "tool_calls": [                    // 本次调用了哪些工具
    {"tool": "calendar", "action": "list", "result_summary": "找到3个事件"}
  ]
}
```

**POST /chat/stream**
```
Request: 同上

Response: SSE stream
event: tool_call
data: {"tool": "calendar", "action": "list", "status": "running"}

event: tool_result
data: {"tool": "calendar", "result": "..."}

event: thinking
data: {"content": "正在整理..."}

event: message
data: {"content": "你今天有3个会议..."}

event: done
data: {"session_id": "sess_a1b2c3d4"}
```

### 4.2 会话管理 API

**POST /sessions** — 创建新会话
```
Request: {"name": "技术方案讨论"}
Response: {"session_id": "sess_a1b2c3d4", "name": "技术方案讨论", "created_at": "..."}
```

**GET /sessions** — 列出所有会话
```
Response: {
  "sessions": [
    {
      "session_id": "sess_a1b2c3d4",
      "name": "工作规划",
      "message_count": 23,
      "last_active": "2026-04-30T14:30:00",
      "summary": "讨论了RBAC方案和权限设计...",
      "is_active": true
    },
    ...
  ],
  "active_session_id": "sess_a1b2c3d4"
}
```

**GET /sessions/{session_id}** — 会话详情
```
Response: {
  "session_id": "...",
  "name": "...",
  "messages": [...],          // 完整对话历史
  "summary": "...",
  "token_stats": {
    "message_count": 23,
    "estimated_tokens": 4200,
    "compression_trigger": 160000
  }
}
```

**POST /sessions/{session_id}/activate** — 切换到此会话
```
Response: {"ok": true, "active_session": "sess_a1b2c3d4"}
```

### 4.3 系统指令 API

系统指令仍走 `/chat`，Agent Server 在进入 LLM 前拦截：

| 指令 | 行为 |
|------|------|
| `/new <name>` | 创建新会话并切换 |
| `/switch <id>` | 切换到指定会话，支持模糊匹配（`/switch sess_a`） |
| `/switch` | 列出所有会话及摘要，供选择 |
| `/sessions` | 同 `/switch`，显示会话列表 |
| `/rename <name>` | 重命名当前会话 |
| `/reset` | 重置当前会话记忆（现有功能，不变） |
| `/compact` | 压缩当前会话上下文（现有功能，不变） |
| `/status` | 当前会话状态 + token 统计（现有功能，扩展） |
| `/help` | 帮助（现有功能，扩展） |

---

## 五、系统指令详细设计

### 5.1 `/new` — 创建新会话

```
用户: /new 技术讨论
Agent: 已创建会话「技术讨论」(sess_b5e6f7a8)。已切换到该会话。
```

- 自动生成 session_id
- 继承当前会话的 profile 信息（时区、偏好）
- 旧会话保持独立，可随时切回

### 5.2 `/switch` — 切换/查看会话

```
# 列出会话
用户: /switch
Agent: 当前活跃: 「工作规划」(sess_a1b2c3d4)

       会话列表:
       [活跃] 工作规划 (sess_a1b2c) — 23条消息 — 最后活跃14:30
              技术讨论 (sess_b5e6f) — 5条消息  — 最后活跃12:10
              读书笔记 (sess_d9e1a) — 8条消息  — 最后活跃昨天

       输入 /switch <id> 切换到对应会话。

# 切换
用户: /switch sess_b5
Agent: 已切换到会话「技术讨论」(sess_b5e6f7a8)。上次话题：讨论了微服务拆分方案。
```

- ID 支持前缀模糊匹配（前4位唯一即可）
- 切换时显示该会话的摘要，帮助用户回忆上下文

### 5.3 `/rename` — 重命名

```
用户: /rename 工作规划 & RBAC
Agent: 会话已重命名为「工作规划 & RBAC」
```

### 5.4 `/status` — 扩展版

```
用户: /status
Agent: 📊 「工作规划」会话状态

       • 消息数: 23 (用户:8 AI:10 工具:5)
       • Token 占用: 4,200 / 160,000 (2.6%)
       • 摘要长度: 186 字符
       • 距压缩触发: 约 155,800 tokens
       • 内存窗口: 最近 8 条消息

       工具: calendar, todo, notes, rag_search
```

---

## 六、通道适配

各通道只做三件事：收消息 → 调 Agent Server → 发回复。

### 6.1 Feishu Bot

```
当前: 飞书 Bot 进程内跑 Agent + Tools + Memory
改为: 飞书 Bot 收到消息 → HTTP POST /chat → 发回复
```

无需大改，`_process_message` 改为 HTTP 调用即可。Bot 本身仍保持 WebSocket 长连接（飞书要求）。

### 6.2 Web (Chainlit)

```
当前: Chainlit 进程内跑 Agent + Tools + Memory
改为: Chainlit 收到消息 → SSE POST /chat/stream → 流式渲染
```

Chainlit 原生支持 streaming，SSE 事件映射到 Chainlit 的 Step/Message。

---

## 七、启动方式

```
# 启动 Agent Server
python run_server.py           # 监听 localhost:8700

# 启动飞书 Bot（连接 Agent Server）
python run_feishu.py           # FEISHU_AGENT_URL=http://localhost:8700

# 启动 Web（连接 Agent Server）
chainlit run src/chainlit_app.py  # AGENT_SERVER_URL=http://localhost:8700
```

统一 `run.py` 可同时启动三者。

---

## 八、实现顺序

| 阶段 | 内容 | 产出 |
|------|------|------|
| 1 | FastAPI Server + SessionManager | `/chat` 可用，单会话 |
| 2 | 多会话 + 系统指令 | `/new` `/switch` `/sessions` `/rename` |
| 3 | Feishu Bot 改为 HTTP client | 飞书不再独立跑 Agent |
| 4 | Chainlit 改为 SSE client | Web 不再独立跑 Agent |
| 5 | Web Session 面板 | 可视化切换/创建会话 |
| 6 | 适配 run.py 统一启动 | 一键起所有服务 |

---

## 九、不在范围内

- 用户认证系统（私有部署，无需）
- 会话持久化到数据库（重启丢失，后续加 SQLite）
- QQ/微信通道（架构支持，后续按需接入）
- 多用户并发（单用户场景）
