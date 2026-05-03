import logging
from .models import Reminder, RepeatRule, ReminderStatus

logger = logging.getLogger("polaris.reminders.handlers")


class ReminderHandler:
    def __init__(self, channel_manager):
        self.channel_manager = channel_manager

    async def handle(self, reminder: Reminder):
        """处理提醒触发"""
        message = self._format_message(reminder)

        # admin 渠道特殊处理：写入 session 消息
        if reminder.channel == "admin":
            self._push_to_admin_session(reminder, message)
            return

        # 其他渠道：通过 channel 插件发送
        channel = self._get_channel(reminder.channel)
        if channel:
            success = channel.send_message(
                session_id=reminder.session_id,
                message=message,
            )
            if success:
                logger.info(f"提醒已推送: {reminder.id} -> {reminder.channel}")
            else:
                logger.warning(f"提醒推送失败: {reminder.id}")
        else:
            logger.warning(f"渠道未找到: {reminder.channel}")

        # 一次性提醒触发后标记为完成
        if reminder.repeat_rule == RepeatRule.NONE:
            reminder.status = ReminderStatus.CANCELLED

    def _push_to_admin_session(self, reminder: Reminder, message: str):
        """将提醒推送到 admin session"""
        try:
            from src.session.manager import get_session_manager
            session_mgr = self.session_manager or get_session_manager()
            session = session_mgr.get(reminder.session_id)
            if session:
                from langchain_core.messages import AIMessage
                session.memory.add_message(AIMessage(content=message))
                logger.info(f"提醒已推送到 admin session: {reminder.id}")
            else:
                logger.warning(f"Session 未找到: {reminder.session_id}")
        except Exception as e:
            logger.warning(f"推送到 admin session 失败: {e}")

        # 一次性提醒触发后标记为完成
        if reminder.repeat_rule == RepeatRule.NONE:
            reminder.status = ReminderStatus.CANCELLED

    def _get_channel(self, channel_name: str):
        """获取渠道插件"""
        for ch in self.channel_manager._channels:
            if ch.name == channel_name:
                return ch
        return None

    def _format_message(self, reminder: Reminder) -> str:
        """格式化提醒消息"""
        lines = [f"⏰ 提醒：{reminder.title}"]
        if reminder.description:
            lines.append(reminder.description)
        return "\n".join(lines)
