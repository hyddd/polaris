from unittest.mock import patch
from src.tools.rag import RAGSearchTool


@patch("src.data_layer.vector_store.search_notes")
def test_rag_search_finds_note(mock_search):
    mock_search.return_value = [
        {"content": "决定采用 RBAC 模型", "metadata": {"title": "PRD v2 讨论"}, "distance": 0.2},
    ]
    tool = RAGSearchTool(persist_dir="/tmp/chroma", collection_name="test")
    result = tool._run("权限方案")
    assert "RBAC" in result
    assert "PRD v2 讨论" in result


@patch("src.data_layer.vector_store.search_notes")
def test_rag_search_no_results(mock_search):
    mock_search.return_value = []
    tool = RAGSearchTool(persist_dir="/tmp/chroma", collection_name="test")
    result = tool._run("量子计算")
    assert "没有找到" in result
