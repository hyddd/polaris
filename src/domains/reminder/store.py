import json
import threading
from pathlib import Path
from datetime import datetime
from .models import Reminder, ReminderStatus
from src.storage.store import JsonFileStore


class ReminderStore:
    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._store = JsonFileStore(file_path)
        self._lock = threading.Lock()
        self._reminders: dict[str, Reminder] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data.get("reminders", []):
                r = Reminder.from_dict(item)
                self._reminders[r.id] = r

    def _save(self):
        data = {"reminders": [r.to_dict() for r in self._reminders.values()]}
        self._store.save(data)

    def create(self, reminder: Reminder) -> Reminder:
        with self._lock:
            self._reminders[reminder.id] = reminder
            self._save()
        return reminder

    def get(self, reminder_id: str) -> Reminder | None:
        return self._reminders.get(reminder_id)

    def list_active(self) -> list[Reminder]:
        return [r for r in self._reminders.values() if r.status == ReminderStatus.ACTIVE]

    def list_all(self) -> list[Reminder]:
        return list(self._reminders.values())

    def find_by_event_id(self, event_id: str) -> list[Reminder]:
        return [r for r in self._reminders.values() if r.event_id == event_id]

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        with self._lock:
            r = self._reminders.get(reminder_id)
            if not r:
                return None
            for k, v in kwargs.items():
                if hasattr(r, k):
                    setattr(r, k, v)
            self._save()
        return r

    def delete(self, reminder_id: str) -> bool:
        with self._lock:
            if reminder_id in self._reminders:
                del self._reminders[reminder_id]
                self._save()
                return True
        return False
