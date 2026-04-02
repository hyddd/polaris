from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.memory.compressor import ConversationCompressor


def test_no_compression_when_under_limit():
    cc = ConversationCompressor(max_recent=8)
    msgs = [
        HumanMessage(content="你好"),
        AIMessage(content="你好！"),
    ]
    summary, recent = cc.process(msgs)
    assert summary == ""
    assert len(recent) == 2


def test_compresses_overflow():
    cc = ConversationCompressor(max_recent=3)
    msgs = [
        HumanMessage(content="msg1"),
        AIMessage(content="reply1"),
        HumanMessage(content="msg2"),
        AIMessage(content="reply2"),
        HumanMessage(content="msg3"),
    ]
    # Overflow: first 2 go to summarizer, last 3 kept
    # _summarize returns fallback text since no real LLM
    summary, recent = cc.process(msgs)
    assert len(recent) <= 3
    assert len(summary) > 0  # Fallback summary


def test_trim_to_token_budget():
    cc = ConversationCompressor(max_recent=10, max_history_tokens=50)
    msgs = [
        HumanMessage(content="短消息"),
        AIMessage(content="也是短消息"),
        HumanMessage(content="这是一条非常非常非常非常长的消息" * 10),
    ]
    _, recent = cc.process(msgs)
    # The long message + recent should be trimmed
    assert len(recent) >= 1  # At minimum, last message kept


def test_estimate_tokens():
    cc = ConversationCompressor()
    msgs = [HumanMessage(content="你好世界")]  # 4 chars → ~2 tokens
    assert cc._estimate_tokens(msgs) == 2

    msgs = [HumanMessage(content="hello")]  # 5 chars → ~2 tokens
    assert cc._estimate_tokens(msgs) == 2


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
