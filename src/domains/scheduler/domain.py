"""SchedulerDomain — 统一任务调度核心服务。"""

import logging
from datetime import datetime

from src.core.events import event_bus
from .models import ScheduledJob
from .store import JobStore
from .executor import SchedulerExecutor

logger = logging.getLogger("polaris.scheduler")


class SchedulerDomain:
    def __init__(self, store: JobStore, executor: SchedulerExecutor):
        self._store = store
        self._executor = executor

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动 executor，从 store 恢复所有 enabled 的 job。"""
        self._executor.start()
        for job in self._store.list_all():
            if job.enabled:
                self._register_job(job)
        logger.info("调度域已启动，已恢复所有启用任务")

    def shutdown(self):
        self._executor.shutdown()
        logger.info("调度域已关闭")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_jobs(self, handler_type: str | None = None) -> list[ScheduledJob]:
        jobs = self._store.list_all()
        if handler_type:
            jobs = [j for j in jobs if j.handler_type == handler_type]
        return jobs

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._store.get(job_id)

    # ------------------------------------------------------------------
    # 创建任务
    # ------------------------------------------------------------------

    def add_cron_job(self, job_id: str, name: str, trigger_kwargs: dict,
                     handler_type: str, handler_kwargs: dict) -> ScheduledJob:
        now = datetime.now().isoformat()
        job = ScheduledJob(
            id=job_id, name=name, trigger_type="cron",
            trigger_kwargs=trigger_kwargs, handler_type=handler_type,
            handler_kwargs=handler_kwargs, created_at=now,
        )
        self._store.create(job)
        self._register_job(job)
        event_bus.publish("scheduler:job_created",
                          job_id=job_id, name=name, trigger_type="cron")
        logger.info(f"已创建 cron 任务: {job_id} ({name})")
        return job

    def add_date_job(self, job_id: str, name: str, run_date: str,
                     handler_type: str, handler_kwargs: dict) -> ScheduledJob:
        now = datetime.now().isoformat()
        job = ScheduledJob(
            id=job_id, name=name, trigger_type="date",
            trigger_kwargs={"run_date": run_date},
            handler_type=handler_type, handler_kwargs=handler_kwargs,
            created_at=now,
        )
        self._store.create(job)
        self._register_job(job)
        event_bus.publish("scheduler:job_created",
                          job_id=job_id, name=name, trigger_type="date")
        logger.info(f"已创建一次性任务: {job_id} ({name})")
        return job

    def add_interval_job(self, job_id: str, name: str, seconds: int,
                         handler_type: str, handler_kwargs: dict) -> ScheduledJob:
        now = datetime.now().isoformat()
        job = ScheduledJob(
            id=job_id, name=name, trigger_type="interval",
            trigger_kwargs={"seconds": seconds},
            handler_type=handler_type, handler_kwargs=handler_kwargs,
            created_at=now,
        )
        self._store.create(job)
        self._register_job(job)
        event_bus.publish("scheduler:job_created",
                          job_id=job_id, name=name, trigger_type="interval")
        logger.info(f"已创建间隔任务: {job_id} ({name})")
        return job

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    def remove_job(self, job_id: str) -> bool:
        self._executor.remove_job(job_id)
        deleted = self._store.delete(job_id)
        if deleted:
            event_bus.publish("scheduler:job_removed", job_id=job_id)
            logger.info(f"已删除任务: {job_id}")
        return deleted

    def pause_job(self, job_id: str) -> bool:
        job = self._store.get(job_id)
        if not job:
            return False
        self._executor.pause_job(job_id)
        self._store.update(job_id, enabled=False)
        logger.info(f"已暂停任务: {job_id}")
        return True

    def resume_job(self, job_id: str) -> bool:
        job = self._store.get(job_id)
        if not job:
            return False
        self._executor.resume_job(job_id)
        self._store.update(job_id, enabled=True)
        logger.info(f"已恢复任务: {job_id}")
        return True

    def trigger_job(self, job_id: str) -> None:
        """手动触发任务。"""
        job = self._store.get(job_id)
        if not job:
            logger.warning(f"手动触发失败，任务不存在: {job_id}")
            return
        logger.info(f"手动触发任务: {job_id}")
        self._dispatch_handler(job.handler_type, job.handler_kwargs)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _register_job(self, job: ScheduledJob):
        """将 job 注册到 executor。"""
        def _handler_wrapper(**kwargs):
            try:
                event_bus.publish("scheduler:job_triggered",
                                  job_id=job.id, name=job.name)
                self._dispatch_handler(job.handler_type, job.handler_kwargs)
                self._store.update(job.id,
                                   last_run=datetime.now().isoformat(),
                                   run_count=job.run_count + 1)
                # 一次性任务执行后自动清理
                if job.trigger_type == "date":
                    self._store.delete(job.id)
                    logger.info(f"一次性任务已执行并清理: {job.id}")
            except Exception:
                logger.exception(f"任务执行异常: {job.id}")

        if job.trigger_type == "cron":
            self._executor.add_cron_job(
                job.id, job.trigger_kwargs, _handler_wrapper, {})
        elif job.trigger_type == "date":
            run_date = job.trigger_kwargs.get("run_date")
            if run_date:
                from datetime import datetime as dt
                run_date = dt.fromisoformat(run_date)
            self._executor.add_date_job(
                job.id, run_date, _handler_wrapper, {})
        elif job.trigger_type == "interval":
            seconds = job.trigger_kwargs.get("seconds", 60)
            self._executor.add_interval_job(
                job.id, seconds, _handler_wrapper, {})

    def _dispatch_handler(self, handler_type: str, handler_kwargs: dict):
        """分发 handler 调用。"""
        if handler_type == "reminder":
            reminder_id = handler_kwargs.get("reminder_id")
            if reminder_id:
                from src.domains.reminder import get_reminder_domain
                domain = get_reminder_domain()
                if domain:
                    domain.trigger(reminder_id)
                else:
                    logger.warning("ReminderDomain 未就绪")
            else:
                logger.warning("reminder handler 缺少 reminder_id")
        elif handler_type == "heartbeat":
            logger.info("心跳任务触发")
        elif handler_type == "daily":
            event_bus.publish("cleanup:cron")
        elif handler_type == "custom":
            callable_path = handler_kwargs.get("callable")
            if callable_path:
                module_path, func_name = callable_path.rsplit(".", 1)
                import importlib
                mod = importlib.import_module(module_path)
                func = getattr(mod, func_name)
                func(**{k: v for k, v in handler_kwargs.items() if k != "callable"})
            else:
                logger.warning("custom handler 缺少 callable 参数")
        else:
            logger.warning(f"未知 handler 类型: {handler_type}")


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: SchedulerDomain | None = None


def get_scheduler_domain() -> SchedulerDomain:
    return _domain


def set_scheduler_domain(domain: SchedulerDomain):
    global _domain
    _domain = domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(cron=None, **kwargs):
    from src.core.config import config
    path = str(config.resolve_path(
        config.get("storage.scheduler_file", "data/scheduler.json")))
    store = JobStore(path)
    executor = SchedulerExecutor()
    domain = SchedulerDomain(store, executor)
    set_scheduler_domain(domain)
    domain.start()


event_bus.subscribe("app:startup", _on_startup)
