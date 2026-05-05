"""SchedulerExecutor — APScheduler 封装。"""

import logging

logger = logging.getLogger("polaris.scheduler.executor")


class SchedulerExecutor:
    def __init__(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        self._scheduler = BackgroundScheduler()

    def start(self):
        self._scheduler.start()
        logger.info("调度执行器已启动")

    def shutdown(self):
        self._scheduler.shutdown()
        logger.info("调度执行器已关闭")

    def add_date_job(self, job_id: str, run_date, handler, handler_kwargs: dict):
        """添加一次性任务。"""
        from apscheduler.triggers.date import DateTrigger
        trigger = DateTrigger(run_date=run_date)
        self._scheduler.add_job(
            handler, trigger=trigger, id=job_id,
            kwargs=handler_kwargs, replace_existing=True,
        )

    def add_cron_job(self, job_id: str, cron_kwargs: dict, handler, handler_kwargs: dict):
        """添加 cron 重复任务。"""
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger(**cron_kwargs)
        self._scheduler.add_job(
            handler, trigger=trigger, id=job_id,
            kwargs=handler_kwargs, replace_existing=True,
        )

    def add_interval_job(self, job_id: str, seconds: int, handler, handler_kwargs: dict):
        """添加间隔任务。"""
        from apscheduler.triggers.interval import IntervalTrigger
        trigger = IntervalTrigger(seconds=seconds)
        self._scheduler.add_job(
            handler, trigger=trigger, id=job_id,
            kwargs=handler_kwargs, replace_existing=True,
        )

    def remove_job(self, job_id: str):
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def pause_job(self, job_id: str):
        try:
            self._scheduler.pause_job(job_id)
        except Exception:
            pass

    def resume_job(self, job_id: str):
        try:
            self._scheduler.resume_job(job_id)
        except Exception:
            pass

    def get_job_info(self, job_id: str) -> dict | None:
        """返回 next_run_time 等信息。"""
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        info = {"id": job.id}
        if job.next_run_time:
            info["next_run_time"] = job.next_run_time.isoformat()
        return info
