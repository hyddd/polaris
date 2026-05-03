import logging
from .models import Reminder, RepeatRule, ReminderStatus

logger = logging.getLogger("polaris.reminders.handlers")


class ReminderHandler:
    def __init__(self, channel_manager):
        self.channel_manager = channel_manager

    async def handle(self, reminder: Reminder):
        """处理提醒触发"""
        message = self._format_message(reminder)

        # 获取渠道并发送消息
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
