"""LLM Provider protocol."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 提供者协议"""

    def chat(self, messages, tools=None, streaming: bool = False): ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
