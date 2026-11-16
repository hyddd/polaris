import logging
from .models import Reminder, RepeatRule, ReminderStatus

logger = logging.getLogger("polaris.reminders.handlers")


class ReminderHandler:
    def __init__(self, channels: list, store=None):
        self._channels = channels
        self._store = store

    def handle(self, reminder: Reminder) -> bool:
        """处理提醒触发（同步函数，APScheduler 直接调用）。返回是否送达。"""
        logger.info(f"提醒触发: {reminder.id} - {reminder.title}")
        message = self._format_message(reminder)

        # 提取渠道名（qq:user123 -> qq）
        channel_name = reminder.channel.split(":")[0] if reminder.channel else ""

        # admin 渠道特殊处理：写入 session 消息
        if channel_name == "admin":
            delivered = self._push_to_admin_session(reminder, message)
        else:
            delivered = self._send_via_channel(reminder, channel_name, message)

        # 一次性提醒：送达才算完成；没送达标 failed，不能伪装成已完成
        if reminder.repeat_rule == RepeatRule.NONE:
            status = ReminderStatus.CANCELLED if delivered else ReminderStatus.FAILED
            reminder.status = status
            if self._store:
                try:
                    self._store.update(reminder.id, status=status)
                except Exception as e:
                    # 公共提醒触发时团队服务恰好连不上：本机已经推送，共享状态留给其他实例或下次同步
                    logger.warning(f"提醒状态更新失败（不影响本次推送）: {reminder.id} - {e}")
            if delivered:
                logger.info(f"提醒已标记为完成: {reminder.id}")
            else:
                logger.error(f"提醒未送达，已标记为 failed（可在提醒页点恢复重投）: {reminder.id} - {reminder.title}")
        elif not delivered:
            logger.error(f"周期提醒本次未送达: {reminder.id} - {reminder.title}")
        return delivered

    def _send_via_channel(self, reminder: Reminder, channel_name: str, message: str) -> bool:
        """其他渠道：通过 channel 插件发送"""
        channel_plugin = self._get_channel(channel_name)
        if not channel_plugin:
            logger.warning(f"渠道未找到: {channel_name or '（未设置）'}")
            return False
        try:
            success = channel_plugin.send_message(
                session_id=reminder.session_id,
                message=message,
                channel=reminder.channel,
            )
        except Exception as e:
            logger.warning(f"提醒推送异常: {reminder.id} ({e})")
            return False
        if success:
            logger.info(f"提醒已推送: {reminder.id} -> {reminder.channel}")
        else:
            logger.warning(f"提醒推送失败: {reminder.id}")
        return bool(success)

    def _push_to_admin_session(self, reminder: Reminder, message: str) -> bool:
        """将提醒推送到 admin session 并立即落盘。

        绑定的会话不存在时（网页日历/提醒接口创建时没绑定会话，或会话后来被删了），
        改投网页当前激活的会话，而不是丢掉。
        这里不拿会话锁：如果该会话正在跑一轮对话，本轮结束写回时会保留这条消息
        （MemoryManager.replace_keeping_appended），不会被覆盖。
        """
        try:
            from src.session.manager import get_session_manager
            from langchain_core.messages import AIMessage
            session_mgr = get_session_manager()
            session = session_mgr.get(reminder.session_id) if reminder.session_id else None
            if session is None:
                session = session_mgr.active_session("admin")
                logger.warning(
                    f"提醒 {reminder.id} 绑定的会话不存在（{reminder.session_id or '未绑定'}），"
                    f"改投网页当前会话 {session.session_id}"
                )
            session.memory.add_message(AIMessage(content=message))
            session_mgr.save_session(session.session_id)
            logger.info(f"提醒已推送到 admin session: {reminder.id} -> {session.session_id}")
            return True
        except Exception as e:
            logger.error(f"推送到 admin session 失败: {reminder.id} ({e})")
            return False

    def _get_channel(self, channel_name: str):
        """获取渠道插件"""
        for ch in self._channels:
            if ch.name == channel_name:
                return ch
        return None

    def _format_message(self, reminder: Reminder) -> str:
        """格式化提醒消息"""
        lines = [f"⏰ 提醒：{reminder.title}"]
        if reminder.description:
            lines.append(reminder.description)
        return "\n".join(lines)
