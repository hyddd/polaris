from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "RAGSearchTool":
    """Factory for auto-discovery. Creates a RAGSearchTool with default config."""
    from src.core.config import config
    return RAGSearchTool(
        persist_dir=str(config.resolve_path(config.get("storage.vector_db_dir", "data/chroma"))),
        collection_name="notes",
    )


class RAGInput(BaseModel):
    query: str = Field(description="自然语言查询，例如'Polaris用了什么向量库'、'Polaris是什么？'")


class RAGSearchTool(BaseTool):
    name: str = "rag_search"
    description: str = "搜索用户的知识库和所有笔记。当用户提问时用此工具。输入自然语言，返回语义匹配的内容。"
    args_schema: type[BaseModel] = RAGInput
    persist_dir: str = ""
    collection_name: str = "notes"

    def _run(self, query: str) -> str:
        from src.domains.rag import get_rag_domain

        query = query.strip()
        if not query:
            return "请输入搜索内容。"

        domain = get_rag_domain()
        if not domain:
            return "检索服务未就绪，请稍后重试。"

        results = domain.search(query, top_k=5)
        if not results:
            return "没有找到相关笔记。"

        output = []
        for r in results:
            if r.score < 0.3:
                continue
            title = r.title or "未命名"
            output.append(f"## {title} (相关度: {r.score:.0%})\n{r.content[:500]}")

        if not output:
            return "没有找到足够相关的笔记，换个关键词试试？"
        return "\n\n---\n\n".join(output)

    async def _arun(self, query: str) -> str:
        return self._run(query)
