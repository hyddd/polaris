# EventBus 事件参考

> 事件名格式：`<domain>:<entity>_<action>`
> 订阅在模块 `__init__.py` 中声明，模块被 import 时自动完成。

```python
from src.core.events import event_bus

event_bus.subscribe("calendar:event_created", my_handler)  # 订阅
event_bus.publish("calendar:event_created", event_id="...") # 发布
```

---

## 事件总表

### 系统事件

| 事件 | 发布者 | 订阅者 | payload |
|------|--------|--------|---------|
| `app:startup` | server 启动 | reminder、heartbeat、daily-tick 自初始化 | `cron`, `channels` |
| `config:reload` | /reload 命令 | LLM 缓存清理、channel 重启、web_search 刷新 | — |
| `cleanup:now` | /cleanup 命令 | calendar、todo、reminder 清理过期数据 | — |
| `cleanup:cron` | cron 每天 3:00 | 同上 | — |

### Calendar Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `calendar:event_created` | 创建日程 | `event_id`, `title`, `event_time_str`, `channel`, `session_id` | reminder（自动建提醒） |
| `calendar:event_updated` | 更新日程 | `event_id`, `title`, `event_time_str` | reminder（同步更新提醒） |
| `calendar:event_deleted` | 删除日程 | `event_id` | reminder（删除关联提醒） |

### Todo Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `todos:todo_created` | 创建待办 | `todo_id`, `title`, `priority` | — |
| `todos:todo_updated` | 更新待办 | `todo_id`, `title`, `status` | — |
| `todos:todo_deleted` | 删除待办 | `todo_id` | — |

### Notes Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `notes:note_created` | 创建笔记 | `note_id`, `title`, `tags` | — |
| `notes:note_updated` | 更新笔记 | `note_id`, `title`, `tags` | — |
| `notes:note_deleted` | 删除笔记 | `note_id` | — |

### Persona Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `persona:persona_changed` | 修改人设 | `session_id`, `name`, `identity` | — |

### Reminder Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `reminder:reminder_created` | 创建提醒 | `reminder_id`, `title`, `trigger_time` | — |
| `reminder:reminder_updated` | 更新提醒 | `reminder_id`, `title`, `trigger_time` | — |
| `reminder:reminder_deleted` | 删除提醒 | `reminder_id` | — |
| `reminder:triggered` | 提醒触发 | `reminder_id`, `title`, `channel`, `session_id` | — |

### RAG Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `rag:document_indexed` | 文档索引完成 | `doc_id`, `filename`, `chunk_count` | — |
| `rag:document_removed` | 文档删除 | `doc_id` | — |

### Scheduler Domain

| 事件 | 触发时机 | payload | 当前订阅者 |
|------|----------|---------|-----------|
| `scheduler:job_created` | 注册定时任务 | `job_id`, `name`, `trigger_type` | — |
| `scheduler:job_removed` | 移除定时任务 | `job_id` | — |
| `scheduler:job_triggered` | 任务触发执行 | `job_id`, `name` | — |
| `scheduler:job_missed` | 任务错过执行 | `job_id`, `name`, `scheduled_time` | — |

---

## 事件命名规范

- 格式：`<domain>:<entity>_<action>`
- domain：小写，与 Domain 目录名一致
- entity：单数名词（event / todo / note / reminder / job / document）
- action：`created` / `updated` / `deleted` / `triggered` / `changed` / `missed`
- 系统事件例外：`app:startup`、`config:reload`、`cleanup:now`

## 订阅规范

- 订阅声明在模块的 `__init__.py` 中，import 时自动完成
- handler 函数命名：`_on_<event_name>`（下划线替换冒号和点）
- handler 必须 try/except，不能让异常传播到 EventBus
- 只读操作不发事件，只有写操作（create/update/delete）才发

## 新增事件清单

新增 Domain 时必须为所有写操作注册事件：

```python
# domains/xxx/__init__.py
from src.core.events import event_bus
from .domain import _on_xxx_created, _on_xxx_updated, _on_xxx_deleted

event_bus.subscribe("xxx:xxx_created", _on_xxx_created)
event_bus.subscribe("xxx:xxx_updated", _on_xxx_updated)
event_bus.subscribe("xxx:xxx_deleted", _on_xxx_deleted)
```
