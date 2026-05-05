"""LLM Provider abstraction layer."""

from .protocol import LLMProvider
from .openai import create_chat_model
