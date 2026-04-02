# 上下文管理与记忆压缩 设计文档

- **版本**: v1.0
- **日期**: 2026-04-30
- **状态**: Draft

---

## 一、问题分析

### 1.1 当前状态

```
MemoryManager (window_size=10)
  └── messages: [msg1, msg2, ..., msg10]  (超出直接丢弃)
       ↓
  Agent Node: 全部塞入 LLM prompt (无 token 感知)
```

| 问题 | 影响 |
|------|------|
| ReAct 循环每轮产生 2 条消息（AI tool_call + Tool result） | 10 条窗口 = 最多 3-4 轮工具调用后丢失历史 |
| 无 token 计数 | 长消息组合超过模型上限时 API 报错 |
| 旧消息直接丢弃 | 早期对话上下文完全丢失 |
| 每次 LLM 调用传全量历史 | token 浪费：闲聊历史对当前工具调用无帮助 |

### 1.2 典型场景分析

用户："帮我准备下午3点的会" → Agent 调用 calendar search → Agent 调用 rag_search → Agent 调用 todo search → Agent 生成回复

消息增长：1 (user) + 2 (tool_call+tool) + 2 + 2 + 1 (final) = 8 条。第二轮对话直接溢出。

---

## 二、方案设计

### 2.1 核心思路：双层记忆

```
┌─────────────────────────────────────────┐
│              双层记忆架构                  │
├─────────────────────────────────────────┤
│  摘要层 (Summary)                        │
│  "用户叫小明，之前讨论了RBAC方案..."       │
│  持久存储，增量更新，注入 system prompt    │
├─────────────────────────────────────────┤
│  最近消息 (Recent Messages)              │
│  [user_msg, tool_call, tool_result, ...] │
│  保留最近 N 条 + token 预算截断           │
└─────────────────────────────────────────┘
```

- **摘要层**：压缩的对话记忆，长周期
- **最近消息层**：完整的近期对话，短周期

### 2.2 压缩触发时机

不是每次发消息都压缩，而是在消息数超过窗口时触发：

```
消息数 ≤ window_size  →  不压缩，全量传入
消息数 > window_size  →  取最早的 overflow 条 → LLM 摘要 → 合并到 summary
```

默认 `window_size = 8`，即有 8 条以上消息时才压缩最早的溢出部分。

### 2.3 Token 预算截断

在传入 LLM 前，对最近消息做 token 估算：

1. 从最新消息开始累加 token 数
2. 超过 `MAX_HISTORY_TOKENS`（默认 4000）时截断
3. 当前用户消息始终保留，不被截断
4. 工具调用链（连续的 tool_call + tool_result）按组保留，不从中截断

### 2.4 摘要 Prompt 设计

```
根据以下对话内容，生成一段简洁的摘要（2-3句话），
包含关键信息：用户身份、重要讨论主题、已执行的工具操作和结果。

已有摘要：{existing_summary}
新对话内容：{new_messages}

请输出更新后的完整摘要：
```

每次摘要调用约消耗 200-500 token（输入已有摘要 + 新消息 + prompt），远低于保留原始消息的成本。

### 2.5 System Prompt 注入

```
今天是 {date}。

[对话摘要]
{summary}

[最近对话]
{recent_messages}

{核心系统提示词}
```

---

## 三、技术实现

### 3.1 新增模块

```
src/memory/
├── store.py          # 现有 MemoryManager（保留）
└── compressor.py     # 新增：ConversationCompressor
```

### 3.2 ConversationCompressor

```python
class ConversationCompressor:
    def __init__(self, max_recent=8, max_history_tokens=4000):
        self.summary = ""
        self.max_recent = max_recent
        self.max_history_tokens = max_history_tokens

    def process(self, messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
        """处理消息列表，返回 (summary, trimmed_messages)。"""
        if len(messages) <= self.max_recent:
            return self.summary, messages

        overflow = messages[:-self.max_recent]
        recent = messages[-self.max_recent:]

        self.summary = self._summarize(self.summary, overflow)
        recent = self._trim_to_budget(recent)

        return self.summary, recent

    def _summarize(self, existing: str, new_messages: list) -> str:
        """调用 LLM 将新消息合并到摘要。"""

    def _trim_to_budget(self, messages: list) -> list:
        """从旧到新截断，直到满足 token 预算。"""

    def _estimate_tokens(self, messages: list) -> int:
        """粗略 token 估算（字符数 / 2，中文约 1 char = 1 token）。"""
```

### 3.3 集成点

**Agent Node (`executor.py`)** — 在构建 prompt 前压缩：

```python
def agent_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    summary, recent = compressor.process(list(messages))

    system_prompt = f"今天是 {today}。\n\n"
    if summary:
        system_prompt += f"[对话摘要]\n{summary}\n\n"
    system_prompt += UNIFIED_SYSTEM_PROMPT

    # 用 recent 而非全部 messages 构建 prompt
    ...
```

**MemoryManager** — 无需改动，compressor 作为独立组件在 agent_node 中使用。

### 3.4 配置项

```bash
# .env
POLARIS_MAX_RECENT=8          # 保留的最近消息数（默认8）
POLARIS_MAX_HISTORY_TOKENS=4000  # 历史消息 token 预算（默认4000）
```

---

## 四、预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 每次 LLM 调用的历史消息 | 全部 10 条 | 最多 8 条 + 摘要 |
| 长对话 token 消耗 | 线性增长，超出报错 | 有界（摘要 + 预算截断） |
| 多轮工具调用承载 | 3-4 轮后丢失上下文 | 摘要保留关键信息，无上限 |
| 额外 LLM 调用 | 0 | 每 N 条消息触发 1 次摘要调用 |

---

## 五、取舍与风险

| 取舍 | 说明 |
|------|------|
| 摘要调用消耗 token | 每次压缩约 200-500 token，但使长对话成为可能 |
| 摘要可能丢失细节 | 摘要天然有损，关键信息可能在压缩中变形 |
| Token 估算不精确 | 用字符数/2 估算，对中英文混合场景有偏差但不影响可用性 |
| 工具调用链保护 | 连续 tool_call+tool_result 作为整体保留，不受截断 |

## 六、后续优化方向

1. **结构化摘要**：摘要中包含"用户偏好""待办列表""讨论中的话题"等结构
2. **向量化长期记忆**：超长周期记忆存入 ChromaDB，RAG 检索
3. **分层摘要**：按重要性分级存储（核心 vs 背景）
4. **tiktoken 精确计数**：用 tiktoken 替代字符数估算
