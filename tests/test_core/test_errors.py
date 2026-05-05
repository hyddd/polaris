"""Tests for src.core.errors — 标准错误体系。"""

from src.core.errors import (
    ToolError,
    ValidationError,
    NotFoundError,
    ExternalServiceError,
    format_tool_error,
)


def test_tool_error_with_suggestion():
    """ToolError 格式化包含建议。"""
    e = ToolError("连接超时", suggestion="请检查网络后重试")
    result = format_tool_error(e)
    assert "❌ 连接超时" in result
    assert "💡 请检查网络后重试" in result


def test_tool_error_without_suggestion():
    """无建议时只显示消息。"""
    e = ToolError("连接超时")
    result = format_tool_error(e)
    assert result == "❌ 连接超时"
    assert "💡" not in result


def test_validation_error():
    """ValidationError 是 ToolError 子类。"""
    e = ValidationError("缺少必填参数 title", suggestion="请提供标题")
    assert isinstance(e, ToolError)
    result = format_tool_error(e)
    assert "❌ 缺少必填参数 title" in result
    assert "💡 请提供标题" in result


def test_not_found_error():
    """NotFoundError 是 ToolError 子类。"""
    e = NotFoundError("日程不存在", suggestion="请确认日程 ID 是否正确")
    assert isinstance(e, ToolError)
    result = format_tool_error(e)
    assert "❌ 日程不存在" in result


def test_external_service_error():
    """ExternalServiceError 是 ToolError 子类，带默认 suggestion。"""
    e = ExternalServiceError("API 调用失败")
    assert isinstance(e, ToolError)
    result = format_tool_error(e)
    assert "❌ API 调用失败" in result
    assert "💡 服务暂时不可用，请稍后重试" in result


def test_unknown_error():
    """未知异常返回通用提示。"""
    result = format_tool_error(RuntimeError("unexpected"))
    assert result == "❌ 操作失败，请稍后重试。"
