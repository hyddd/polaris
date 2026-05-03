"""Data cleanup and archival — prevents JSON data files from growing indefinitely."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("polaris.cleanup")


class DataCleanup:
    def __init__(self):
        from src.config import config

        self._enabled = config.get("cleanup.enabled", True)
        self._archive_dir = config.resolve_path(
            config.get("cleanup.archive_dir", "data/archive")
        )
        self._archive_max_age = config.get("cleanup.archive_max_age_days", 30)
        self._reminders_retention = config.get("cleanup.reminders_retention_days", 7)
        self._calendar_retention = config.get("cleanup.calendar_retention_days", 14)
        self._todos_retention = config.get("cleanup.todos_retention_days", 30)

    def run(self) -> dict:
        if not self._enabled:
            logger.info("清理功能已禁用")
            return {"enabled": False}

        summary = {
            "reminders": self._cleanup_reminders(),
            "calendar": self._cleanup_calendar(),
            "todos": self._cleanup_todos(),
            "archive_deleted": self._cleanup_archive_dir(),
        }
        total = sum(v for v in summary.values() if isinstance(v, int))
        logger.info(f"清理完成: 共处理 {total} 条")
        return summary

    # ── Reminders ──────────────────────────────────────────────

    def _cleanup_reminders(self) -> int:
        from src.config import config

        path = config.resolve_path(
            config.get("storage.reminders_file", "data/reminders.json")
        )
        if not path.exists():
            return 0

        data = json.loads(path.read_text(encoding="utf-8"))
        reminders = data.get("reminders", [])
        cutoff = datetime.now() - timedelta(days=self._reminders_retention)

        to_archive, kept = [], []
        for r in reminders:
            trigger_time = datetime.fromisoformat(r["trigger_time"])
            if r.get("status") == "cancelled" and trigger_time < cutoff:
                to_archive.append(r)
            else:
                kept.append(r)

        if to_archive:
            self._write_archive("reminders", to_archive)
            data["reminders"] = kept
            self._atomic_write(path, data)
            logger.info(f"提醒: 归档 {len(to_archive)} 条，保留 {len(kept)} 条")
        return len(to_archive)

    # ── Calendar ───────────────────────────────────────────────

    def _cleanup_calendar(self) -> int:
        from src.config import config

        path = config.resolve_path(
            config.get("storage.calendar_file", "data/calendar.json")
        )
        if not path.exists():
            return 0

        raw = json.loads(path.read_text(encoding="utf-8"))
        events = raw if isinstance(raw, list) else []
        cutoff = (datetime.now() - timedelta(days=self._calendar_retention)).strftime(
            "%Y-%m-%d"
        )

        to_archive, kept = [], []
        for e in events:
            if e.get("date", "") < cutoff:
                to_archive.append(e)
            else:
                kept.append(e)

        if to_archive:
            self._write_archive("calendar", to_archive)
            self._atomic_write(path, kept)
            logger.info(f"日程: 归档 {len(to_archive)} 条，保留 {len(kept)} 条")
        return len(to_archive)

    # ── Todos ──────────────────────────────────────────────────

    def _cleanup_todos(self) -> int:
        from src.config import config

        path = config.resolve_path(
            config.get("storage.todos_file", "data/todos.json")
        )
        if not path.exists():
            return 0

        raw = json.loads(path.read_text(encoding="utf-8"))
        todos = raw if isinstance(raw, list) else []

        to_archive, kept = [], []
        for t in todos:
            if t.get("done"):
                to_archive.append(t)
            else:
                kept.append(t)

        if to_archive:
            self._write_archive("todos", to_archive)
            self._atomic_write(path, kept)
            logger.info(f"待办: 归档 {len(to_archive)} 条，保留 {len(kept)} 条")
        return len(to_archive)

    # ── Archive ────────────────────────────────────────────────

    def _write_archive(self, data_type: str, records: list[dict]) -> None:
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        month = datetime.now().strftime("%Y-%m")
        archive_path = self._archive_dir / f"{data_type}-{month}.json"

        existing = []
        if archive_path.exists():
            existing = json.loads(archive_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []

        existing.extend(records)
        archive_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _cleanup_archive_dir(self) -> int:
        if not self._archive_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=self._archive_max_age)
        deleted = 0
        for f in self._archive_dir.iterdir():
            if not f.is_file() or f.suffix != ".json":
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
                logger.info(f"删除过期归档: {f.name}")
        return deleted

    # ── Atomic write ───────────────────────────────────────────

    @staticmethod
    def _atomic_write(path: Path, data) -> None:
        import shutil
        import tempfile

        backup = path.with_suffix(path.suffix + ".bak")
        if path.exists():
            shutil.copy2(path, backup)

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            Path(tmp).rename(path)
            if backup.exists():
                backup.unlink()
        except Exception:
            if Path(tmp).exists():
                Path(tmp).unlink()
            if backup.exists():
                shutil.copy2(backup, path)
                backup.unlink()
            raise
