"""JobStore — 调度任务 JSON 文件持久化。"""

import json
import logging
import threading
from pathlib import Path

from src.core.storage.store import JsonFileStore
from .models import ScheduledJob

logger = logging.getLogger("polaris.scheduler.store")


class JobStore:
    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._store = JsonFileStore(file_path)
        self._lock = threading.Lock()
        self._jobs: dict[str, ScheduledJob] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data.get("jobs", []):
                job = ScheduledJob.from_dict(item)
                self._jobs[job.id] = job
            logger.info(f"已加载 {len(self._jobs)} 个调度任务")

    def _save(self):
        data = {"jobs": [j.to_dict() for j in self._jobs.values()]}
        self._store.save(data)

    def create(self, job: ScheduledJob) -> ScheduledJob:
        with self._lock:
            self._jobs[job.id] = job
            self._save()
        return job

    def get(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[ScheduledJob]:
        return list(self._jobs.values())

    def update(self, job_id: str, **kwargs) -> ScheduledJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for k, v in kwargs.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            self._save()
        return job

    def delete(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save()
                return True
        return False
