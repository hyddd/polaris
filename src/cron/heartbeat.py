"""Heartbeat task — periodically sends a prompt to LLM and pushes result to channel."""

import logging

logger = logging.getLogger("polaris.heartbeat")


class HeartbeatTask:
    def __init__(self, cron, channels: list):
        from src.core.config import config

        self._cron = cron
        self._channels = channels
        self._enabled = config.get("heartbeat.enabled", False)
        self._interval = config.get("heartbeat.interval_minutes", 60)
        self._channel_name = config.get("heartbeat.channel", "")
        self._prompt_file = config.resolve_path(
            config.get("heartbeat.prompt_file", "data/heartbeat.md")
        )

    def start(self):
        if not self._enabled:
            logger.info("心跳任务未启用")
            return
        if not self._channel_name:
            logger.warning("心跳任务未绑定 channel")
            return

        self._cron.add_interval_job(self._run, "heartbeat", minutes=self._interval)
        logger.info(
            f"心跳任务已注册: 每 {self._interval} 分钟 → {self._channel_name}"
        )

    def _run(self):
        if not self._prompt_file.exists():
            self._notify(f"心跳任务已启用，但提示文件不存在：{self._prompt_file}")
            return

        prompt = self._prompt_file.read_text(encoding="utf-8").strip()
        if not prompt:
            self._notify("心跳任务已启用，但提示文件内容为空。")
            return

        logger.info(f"心跳触发: {len(prompt)} 字符 → {self._channel_name}")

        import asyncio
        from src.session.manager import get_session_manager
        from src.message import process_message

        session_mgr = get_session_manager()

        try:
            results = asyncio.run(
                process_message(prompt, session_mgr, channel=self._channel_name)
            )
            response_text, _ = results[-1]
        except Exception as e:
            logger.error(f"心跳 LLM 调用失败: {e}")
            return

        session = session_mgr.active_session(self._channel_name)
        ch = self._get_channel()
        if ch:
            ch.send_message(
                session_id=session.session_id,
                message=response_text or "（心跳任务无响应）",
                channel=self._channel_name,
            )

    def _notify(self, message: str):
        """直接推送通知到绑定 channel，不走 LLM。"""
        logger.warning(message)
        ch = self._get_channel()
        if not ch:
            return
        from src.session.manager import get_session_manager
        session_mgr = get_session_manager()
        session = session_mgr.active_session(self._channel_name)
        ch.send_message(
            session_id=session.session_id,
            message=message,
            channel=self._channel_name,
        )

    def _get_channel(self):
        # channel_name 可能是 "qq:具体用户ID"，按 : 拆分取 channel 名
        name = self._channel_name.split(":")[0]
        for c in self._channels:
            if c.name == name:
                return c
        logger.warning(f"心跳绑定的 channel 未找到: {self._channel_name}")
        return None


def _on_startup(cron=None, channels=None, **kwargs):
    HeartbeatTask(cron, channels or []).start()


from src.core.events import event_bus
event_bus.subscribe("app:startup", _on_startup)
