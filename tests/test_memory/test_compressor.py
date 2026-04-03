from langchain_core.messages import HumanMessage, AIMessage
from src.memory.compressor import ConversationCompressor


def test_no_compression_under_budget():
    """Small messages, large context → no compression."""
    cc = ConversationCompressor(model_max_context=200000, compression_threshold=0.8)
    msgs = [
        HumanMessage(content="你好"),
        AIMessage(content="你好！"),
    ]
    summary, recent = cc.process(msgs)
    assert summary == ""
    assert len(recent) == 2


def test_compression_when_over_budget():
    """Tiny context window → immediate compression."""
    cc = ConversationCompressor(model_max_context=200, compression_threshold=0.8)
    # Create messages that overflow the tiny budget
    msgs = [
        HumanMessage(content="这是一条测试消息" * 20),
        AIMessage(content="这是回复消息" * 20),
        HumanMessage(content="这是第二条测试消息" * 20),
    ]
    summary, recent = cc.process(msgs)
    # Should have compressed — summary non-empty or recent < original
    assert len(summary) > 0 or len(recent) < len(msgs)


def test_count_tokens():
    cc = ConversationCompressor()
    # Chinese: roughly 1 token per char
    assert cc._count_tokens_str("你好世界") >= 2  # 4 chars
    assert cc._count_tokens_str("hello") >= 2      # 5 chars
    assert cc._count_tokens_str("") == 0           # empty

    msgs = [HumanMessage(content="你好世界")]
    assert cc._count_tokens(msgs) >= 2


def test_messages_to_text():
    cc = ConversationCompressor()
    msgs = [
        HumanMessage(content="今天有什么安排"),
        AIMessage(content="你有3个会议"),
    ]
    text = cc._messages_to_text(msgs)
    assert "今天有什么安排" in text
    assert "你有3个会议" in text
    assert "用户" in text
    assert "助手" in text


def test_find_split_point():
    cc = ConversationCompressor()
    msgs = [
        HumanMessage(content="消息1" * 10),   # ~10 tokens
        AIMessage(content="消息2" * 10),       # ~10 tokens
        HumanMessage(content="消息3" * 10),    # ~10 tokens
    ]
    # target_tokens = 15: should keep last 1 message (split at 2)
    split = cc._find_split_point(msgs, 15)
    assert split >= 1  # At least some messages moved to overflow
