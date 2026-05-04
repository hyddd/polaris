# 架构决策：从意图路由到 ReAct

> 日期: 2026-05-04
> 状态: 已落地

## 背景

Polaris 最初采用**意图路由（Intent Router）**模式：收到用户消息后先分类意图，再走对应的预设流程。例如"查日程"走 calendar pipeline，"创建待办"走 todo pipeline。

随着工具数量增长到 7 个，这套模式暴露出问题：

1. **组合爆炸。** 用户可能在一个请求里同时需要 calendar + todo，"查一下明天有什么安排，顺便帮我把买机票加到待办"。意图路由需要为每种组合硬编码一条分支，7 个工具的理论组合数不可维护。

2. **多步操作需要显式编排。** "把明天下午的会推迟到 3 点"需要先 search（拿 event_id）再 update。意图路由下要么在工具层写调用链，要么让 LLM 分两次请求，用户感知到两次对话轮次。

3. **新增工具要改路由表。** 每个新 tool 都要在意图分类器里加规则，违反了插件化原则。

4. **意图分类本身有歧义。** "帮我记一下下周去体检"——是创建日程还是记笔记还是设提醒？分类错就全错，没有回头路。

## 决策

用 **ReAct（Reasoning + Acting）** 替代意图路由。具体是 LangGraph StateGraph，agent_node ↔ tool_node 循环：

```
用户消息 → command_node → agent_node（LLM 决定调不调工具）
                              ↓
                         tool_node（执行工具 → 结果回 agent_node）
                              ↓
                         agent_node（再决定要不要继续调工具）
                              ↓
                         返回最终回复
```

## 权衡

| | 意图路由 | ReAct |
|---|---|---|
| 多工具组合 | 需硬编码组合分支 | LLM 自主决定 |
| 新增工具 | 改路由表 | 不改任何代码 |
| 多步操作 | 需显式编排 | 天然 observe→act 循环 |
| 延迟 | 低（单次 LLM） | 可能多轮（每次工具调用后 LLM 再走一轮） |
| 可预测性 | 高（规则确定） | 依赖模型判断质量 |
| 拦截确认 | 需额外状态机 | interceptor 嵌入 tool_node 自然处理 |

核心取舍：**灵活换控制**。意图路由可控且快，但不可扩展；ReAct 灵活但每次思考都要走 LLM。

## 当前实现

`src/agent/graph.py` 中的 StateGraph：

```
command → should_end?
  → agent → should_continue?
    → tools → agent（循环）
    → END
```

- `command_node` 拦截 `/` 系统命令，不走 LLM
- `agent_node` 组装 system prompt + 工具列表 + 消息历史，LLM 决定是否调工具
- `tool_node` 执行工具调用，interceptor 在此层拦截（如删除确认）
- `should_continue` 检查最后的 AIMessage 是否有 `tool_calls`，有则继续循环
