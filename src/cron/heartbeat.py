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
            logger.warning(f"心跳提示文件不存在: {self._prompt_file}")
            return

        prompt = self._prompt_file.read_text(encoding="utf-8").strip()
        if not prompt:
            return

        logger.info(f"心跳触发: {len(prompt)} 字符 → {self._channel_name}")

        import asyncio
        from src.session.manager import get_session_manager
        from src.message import process_message

        session_mgr = get_session_manager()
        # 根据 channel→session 绑定关系决定用哪个会话
        session = session_mgr.active_session(self._channel_name)
        channel_key = f"{self._channel_name}:{session.session_id}"

        try:
            response_text, _ = asyncio.run(
                process_message(prompt, session_mgr, channel=channel_key)
            )
        except Exception as e:
            logger.error(f"心跳 LLM 调用失败: {e}")
            return

        ch = self._get_channel()
        if ch:
            ch.send_message(
                session_id=session.session_id,
                message=response_text or "（心跳任务无响应）",
                channel=channel_key,
            )

    def _get_channel(self):
        for c in self._channels:
            if c.name == self._channel_name:
                return c
        logger.warning(f"心跳绑定的 channel 未找到: {self._channel_name}")
        return None
