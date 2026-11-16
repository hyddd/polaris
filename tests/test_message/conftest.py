import pytest


@pytest.fixture(autouse=True)
def _forbid_real_llm(monkeypatch):
    """对话链路测试只能用脚本节点；误用真实 agent 时直接报错，绝不发出网络请求。"""
    def _no_llm():
        raise AssertionError("测试误用了真实 LLM（会发网络请求）")
    monkeypatch.setattr("src.agent.executor._get_llm", _no_llm)
