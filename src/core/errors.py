"""标准错误体系 — 工具执行错误的统一定义与格式化。"""

import logging

logger = logging.getLogger("polaris.errors")


class ToolError(Exception):
    """工具执行错误基类"""
    def __init__(self, message: str, suggestion: str = ""):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ValidationError(ToolError):
    """参数校验错误"""
    pass


class NotFoundError(ToolError):
    """资源不存在"""
    pass


class ExternalServiceError(ToolError):
    """外部服务调用失败"""
    pass


def format_tool_error(e: Exception) -> str:
    """将异常转换为用户友好的错误消息。"""
    if isinstance(e, ToolError):
        msg = f"❌ {e.message}"
        if e.suggestion:
            msg += f"\n💡 {e.suggestion}"
        return msg
    logger.exception("未预期的工具错误")
    return "❌ 操作失败，请稍后重试。"
