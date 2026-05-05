from unittest.mock import patch, MagicMock

from src.domains.rag.models import RAGSearchResult
from src.tools.rag import RAGSearchTool


@patch("src.domains.rag.get_rag_domain")
def test_rag_search_finds_note(mock_get_domain):
    mock_domain = MagicMock()
    mock_domain.search.return_value = [
        RAGSearchResult(
            filename="PRD-v2-讨论.md",
            title="PRD v2 讨论",
            content="决定采用 RBAC 模型",
            score=0.8,
            tags=[],
        ),
    ]
    mock_get_domain.return_value = mock_domain
    tool = RAGSearchTool(persist_dir="/tmp/chroma", collection_name="test")
    result = tool._run(action="search", query="权限方案")
    assert "RBAC" in result
    assert "PRD v2 讨论" in result


@patch("src.domains.rag.get_rag_domain")
def test_rag_search_no_results(mock_get_domain):
    mock_domain = MagicMock()
    mock_domain.search.return_value = []
    mock_get_domain.return_value = mock_domain
    tool = RAGSearchTool(persist_dir="/tmp/chroma", collection_name="test")
    result = tool._run(action="search", query="量子计算")
    assert "没有找到" in result
