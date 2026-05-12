"""OpenAI-compatible LLM provider implementation."""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.core.config import config


def _patch_reasoning_content(llm: ChatOpenAI) -> None:
    """Patch ChatOpenAI to preserve reasoning_content across API calls.

    MiMo/DeepSeek thinking mode returns reasoning_content in responses,
    which must be passed back in subsequent assistant messages. LangChain
    strips this field. This patch:
    1. Captures reasoning_content from streaming/non-streaming responses
    2. Stores it in AIMessage.additional_kwargs
    3. Injects it back into API requests via _convert_message_to_dict
    """
    # 1. Inject reasoning_content into API requests
    orig_payload = llm._get_request_payload

    def _get_request_payload(input_, *, stop=None, **kwargs):
        # Get original message objects to read additional_kwargs
        messages = llm._convert_input(input_).to_messages()
        rc_map = {}
        for m in messages:
            if hasattr(m, "additional_kwargs") and m.additional_kwargs.get("reasoning_content"):
                rc_map[id(m)] = m.additional_kwargs["reasoning_content"]

        payload = orig_payload(input_, stop=stop, **kwargs)

        # Inject reasoning_content into assistant message dicts
        if rc_map:
            for i, m in enumerate(messages):
                rc = rc_map.get(id(m))
                if rc and i < len(payload.get("messages", [])):
                    msg_dict = payload["messages"][i]
                    if msg_dict.get("role") == "assistant":
                        msg_dict["reasoning_content"] = rc
        return payload

    llm._get_request_payload = _get_request_payload

    # 2. Capture reasoning_content from streaming chunks
    orig_convert_chunk = llm._convert_chunk_to_generation_chunk

    def _convert_chunk_to_generation_chunk(chunk, *args, **kwargs):
        gen_chunk = orig_convert_chunk(chunk, *args, **kwargs)
        if gen_chunk and hasattr(gen_chunk, "message"):
            # reasoning_content lives in choices[0].delta
            choices = chunk.get("choices", [])
            if choices and isinstance(choices[0].get("delta"), dict):
                rc = choices[0]["delta"].get("reasoning_content")
                if rc:
                    gen_chunk.message.additional_kwargs["reasoning_content"] = rc
        return gen_chunk

    llm._convert_chunk_to_generation_chunk = _convert_chunk_to_generation_chunk

    # 3. Capture reasoning_content from non-streaming responses
    orig_generate = llm._generate

    def _generate(*args, **kwargs):
        result = orig_generate(*args, **kwargs)
        for gen in result.generations:
            msg = gen.message
            rc = getattr(msg, "reasoning_content", None)
            if rc:
                msg.additional_kwargs["reasoning_content"] = rc
        return result

    llm._generate = _generate


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
        model_kwargs={"tool_choice": "auto"},
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    llm = ChatOpenAI(**kwargs)
    _patch_reasoning_content(llm)
    return llm
