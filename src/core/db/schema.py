"""公共库表结构（兼容 MySQL 5.6）。

5.6 的限制：
- 没有 JSON 类型：标签等数组存 TEXT（JSON 字符串），由代码序列化；
- innodb_large_prefix 关闭时单列索引最长 767 字节：utf8mb4 下可索引的 VARCHAR 最长 191；
- 没有中文全文检索（ngram 是 5.7.6 才有）。
所有表 utf8mb4，表名不加前缀，建议为 Polaris 单独建库。启动时 CREATE TABLE IF NOT EXISTS，不会改动或删除已有表。
"""

TABLES = {
    "todos": """
CREATE TABLE IF NOT EXISTS {t} (
  id          VARCHAR(32)  NOT NULL COMMENT '如 todo-1a2b3c4d',
  title       VARCHAR(500) NOT NULL,
  priority    ENUM('high','medium','low') NOT NULL DEFAULT 'medium',
  status      ENUM('pending','in_progress','done') NOT NULL DEFAULT 'pending',
  due_date    DATE         NULL COMMENT '没有截止日期为 NULL',
  tags        TEXT         NULL COMMENT 'JSON 字符串数组',
  created_at  DATETIME(6)  NOT NULL,
  updated_at  DATETIME(6)  NOT NULL,
  PRIMARY KEY (id),
  KEY idx_status_due (status, due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共待办'""",

    "calendar_events": """
CREATE TABLE IF NOT EXISTS {t} (
  id            VARCHAR(32)       NOT NULL COMMENT '如 evt-1a2b3c4d',
  title         VARCHAR(500)      NOT NULL,
  event_date    DATE              NOT NULL,
  start_time    TIME              NOT NULL DEFAULT '09:00:00',
  duration_min  SMALLINT UNSIGNED NOT NULL DEFAULT 60,
  attendees     TEXT              NULL COMMENT 'JSON 字符串数组',
  created_at    DATETIME(6)       NOT NULL,
  updated_at    DATETIME(6)       NOT NULL,
  PRIMARY KEY (id),
  KEY idx_date_time (event_date, start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共日程'""",

    "reminders": """
CREATE TABLE IF NOT EXISTS {t} (
  id            VARCHAR(32)  NOT NULL COMMENT '如 rmd-1a2b3c4d',
  title         VARCHAR(500) NOT NULL,
  description   TEXT         NULL,
  trigger_time  DATETIME     NOT NULL COMMENT '服务端本地时间、无时区；周期提醒为首次触发时间',
  repeat_rule   ENUM('none','daily','weekly','monthly') NOT NULL DEFAULT 'none',
  status        ENUM('active','paused','cancelled','failed') NOT NULL DEFAULT 'active'
                COMMENT 'cancelled = 一次性提醒已触发',
  event_id      VARCHAR(32)  NULL COMMENT '关联的公共日程',
  created_at    DATETIME(6)  NOT NULL,
  updated_at    DATETIME(6)  NOT NULL,
  PRIMARY KEY (id),
  KEY idx_status_time (status, trigger_time),
  KEY idx_event (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Polaris 公共提醒；每个实例都推送给自己的用户，投递目标不入库'""",

    "notes": """
CREATE TABLE IF NOT EXISTS {t} (
  note_key    VARCHAR(191) NOT NULL COMMENT '笔记标识（文件名形式，如 周会纪要-1a2b3c.md）',
  title       VARCHAR(500) NOT NULL DEFAULT '',
  content     MEDIUMTEXT   NOT NULL,
  tags        TEXT         NULL COMMENT 'JSON 字符串数组',
  note_date   DATE         NULL,
  archived    TINYINT(1)   NOT NULL DEFAULT 0,
  created_at  DATETIME(6)  NOT NULL,
  updated_at  DATETIME(6)  NOT NULL,
  PRIMARY KEY (note_key),
  KEY idx_archived_date (archived, note_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共笔记'""",

    "knowledge_documents": """
CREATE TABLE IF NOT EXISTS {t} (
  doc_id       VARCHAR(64)  NOT NULL,
  filename     VARCHAR(255) NOT NULL,
  chunk_count  INT UNSIGNED NOT NULL DEFAULT 0,
  tags         TEXT         NULL COMMENT 'JSON 字符串数组',
  created_at   DATETIME(6)  NOT NULL,
  PRIMARY KEY (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共知识库文档'""",
}


def ddl(table=lambda name: f"`{name}`") -> list[str]:
    return [sql.strip().format(t=table(name)) for name, sql in TABLES.items()]


def ensure_schema(db) -> None:
    for statement in ddl(db.t):
        db.execute(statement)
