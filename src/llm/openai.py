"""OpenAI-compatible LLM provider implementation."""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def create_chat_model(
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    streaming: bool = False,
) -> ChatOpenAI:
    """创建 ChatOpenAI 实例（使用全局配置）。

    Args:
        temperature: 模型温度参数，控制输出的随机性。
        max_tokens: 最大输出 token 数。None 表示使用模型默认值。
        streaming: 是否启用流式输出。

    Returns:
        ChatOpenAI 实例。
    """
    kwargs: dict = dict(
        model=LLM_MODEL,
        temperature=temperature,
        streaming=streaming,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if LLM_API_KEY:
        kwargs["api_key"] = LLM_API_KEY
    if LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL
    return ChatOpenAI(**kwargs)
