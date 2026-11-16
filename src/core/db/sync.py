"""定期发布 public:sync 事件，让本进程的公共提醒调度和公共数据保持一致。

- team：别人可能直接在数据库里改了提醒（运维手工修数据），定期对一遍再调度；
- personal：从 team 服务拉取公共提醒，在本机提醒自己的用户。
待办、日程、提醒列表每次都直接读公共数据（数据库或 team 接口），不需要同步。
"""
import logging
import threading

from src.core.config import config
from src.core.infra import event_bus

logger = logging.getLogger("polaris.db.sync")

_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop(interval: float) -> None:
    while not _stop.wait(interval):
        try:
            event_bus.publish("public:sync")
        except Exception as e:
            logger.warning(f"公共数据同步事件发布失败：{e}")


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    interval = float(config.get("sync.interval_seconds", 60))
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(interval,), name="public-sync", daemon=True)
    _thread.start()
    logger.info(f"公共数据同步已启动，间隔 {interval:.0f} 秒")


def stop() -> None:
    _stop.set()


def _on_startup(**kwargs):
    from .scope import public_enabled, get_database, instance_info, is_team
    info = instance_info()
    logger.info(f"服务模式：{info['mode_label']}（{info['name']}）"
                + (f"，团队服务 {info.get('remote')}" if not is_team() and info.get("remote") else ""))
    for warning in getattr(config, "warnings", []):
        logger.warning(f"配置提示：{warning}")
    if not public_enabled():
        return
    if is_team():
        try:
            get_database()
        except Exception as e:
            logger.error(f"公共库初始化失败（公共数据暂不可用）：{e}")
    start()


event_bus.subscribe("app:startup", _on_startup)
