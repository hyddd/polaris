"""OpenAI-compatible LLM provider implementation."""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.config import config


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
    model = config.get("llm.model", "gpt-4o")
    api_key = config.get("llm.api_key", "")
    base_url = config.get("llm.base_url", "https://api.openai.com/v1")

    kwargs: dict = dict(
        model=model,
        temperature=temperature,
        streaming=streaming,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)
