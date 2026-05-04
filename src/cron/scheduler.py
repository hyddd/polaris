"""Generic cron scheduler wrapping APScheduler."""

import logging

logger = logging.getLogger("polaris.cron")


class CronScheduler:
    def __init__(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        self._scheduler = BackgroundScheduler()

    def start(self):
        self._scheduler.start()
        logger.info("Cron 调度器已启动")

    def shutdown(self):
        self._scheduler.shutdown()
        logger.info("Cron 调度器已关闭")

    def add_date_job(self, func, run_date, job_id, args=None):
        """添加一次性定时任务"""
        from apscheduler.triggers.date import DateTrigger

        trigger = DateTrigger(run_date=run_date)
        self._scheduler.add_job(
            func, trigger=trigger, args=args or [], id=job_id,
            replace_existing=True,
        )

    def add_cron_job(self, func, job_id, args=None, **cron_kwargs):
        """添加重复定时任务。cron_kwargs 如 hour=3, minute=0"""
        from apscheduler.triggers.cron import CronTrigger

        self._scheduler.add_job(
            func, trigger=CronTrigger(**cron_kwargs),
            args=args or [], id=job_id, replace_existing=True,
        )

    def add_interval_job(self, func, job_id, minutes=60):
        """添加间隔定时任务（每 N 分钟执行一次）。"""
        from apscheduler.triggers.interval import IntervalTrigger

        self._scheduler.add_job(
            func, trigger=IntervalTrigger(minutes=minutes),
            id=job_id, replace_existing=True,
        )

    def remove_job(self, job_id):
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass


# Global instance accessors
_instance: CronScheduler | None = None


def get_cron_scheduler():
    return _instance


def set_cron_scheduler(scheduler):
    global _instance
    _instance = scheduler
