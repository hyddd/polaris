-- Polaris team 模式公共库表结构（MySQL 5.6 及以上，utf8mb4）
--
-- 用途：DBA 手工建表、审核表结构时参考。team 模式首次连接数据库时会自动执行 CREATE TABLE IF NOT EXISTS，
--       正常部署不需要手工执行本文件。
-- 来源：从实际运行的库导出（SHOW CREATE TABLE），与代码中的表定义 src/core/db/schema.py 一致；
--       修改表结构时以 schema.py 为准，并同步更新本文件（tests/test_db/test_schema_sql.py 会检查两者是否一致）。
-- 执行：先按 README 6.1 建库和用户，再在该库中执行：mysql -u polaris -p polaris < deploy/mysql/schema.sql
--       本文件使用 CREATE TABLE（不带 IF NOT EXISTS），表已存在时会报错，不会覆盖已有的表。

-- Create syntax for TABLE 'calendar_events'
CREATE TABLE `calendar_events` (
  `id` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 evt-1a2b3c4d',
  `title` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_date` date NOT NULL,
  `start_time` time NOT NULL DEFAULT '09:00:00',
  `duration_min` smallint(5) unsigned NOT NULL DEFAULT '60',
  `attendees` text COLLATE utf8mb4_unicode_ci COMMENT 'JSON 字符串数组',
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_date_time` (`event_date`,`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共日程';

-- Create syntax for TABLE 'knowledge_documents'
CREATE TABLE `knowledge_documents` (
  `doc_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `chunk_count` int(10) unsigned NOT NULL DEFAULT '0',
  `tags` text COLLATE utf8mb4_unicode_ci COMMENT 'JSON 字符串数组',
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`doc_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共知识库文档';

-- Create syntax for TABLE 'notes'
CREATE TABLE `notes` (
  `note_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '笔记标识（文件名形式，如 周会纪要-1a2b3c.md）',
  `title` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `content` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `tags` text COLLATE utf8mb4_unicode_ci COMMENT 'JSON 字符串数组',
  `note_date` date DEFAULT NULL,
  `archived` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`note_key`),
  KEY `idx_archived_date` (`archived`,`note_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共笔记';

-- Create syntax for TABLE 'reminders'
CREATE TABLE `reminders` (
  `id` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 rmd-1a2b3c4d',
  `title` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `trigger_time` datetime NOT NULL COMMENT '服务端本地时间、无时区；周期提醒为首次触发时间',
  `repeat_rule` enum('none','daily','weekly','monthly') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'none',
  `status` enum('active','paused','cancelled','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT 'cancelled = 一次性提醒已触发',
  `event_id` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关联的公共日程',
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_status_time` (`status`,`trigger_time`),
  KEY `idx_event` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共提醒；每个实例都推送给自己的用户，投递目标不入库';

-- Create syntax for TABLE 'todos'
CREATE TABLE `todos` (
  `id` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 todo-1a2b3c4d',
  `title` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `priority` enum('high','medium','low') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'medium',
  `status` enum('pending','in_progress','done') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `due_date` date DEFAULT NULL COMMENT '没有截止日期为 NULL',
  `tags` text COLLATE utf8mb4_unicode_ci COMMENT 'JSON 字符串数组',
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_status_due` (`status`,`due_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Polaris 公共待办';
