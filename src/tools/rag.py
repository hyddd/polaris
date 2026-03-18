from langchain_core.tools import BaseTool


class RAGSearchTool(BaseTool):
    name: str = "rag_search"
    description: str = "Semantic search across your notes. Input: a natural language query string."
    persist_dir: str = ""
    collection_name: str = "notes"

    def _run(self, query: str) -> str:
        from src.data_layer.vector_store import search_notes

        query = query.strip()
        if not query:
            return "请输入搜索内容。"

        results = search_notes(query, self.persist_dir, self.collection_name)
        if not results:
            return "没有找到相关笔记。"

        output = []
        for r in results:
            similarity = max(0, 1 - r.get("distance", 0))
            if similarity < 0.3:
                continue
            title = r["metadata"].get("title", "未命名")
            output.append(f"## {title} (相关度: {similarity:.0%})\n{r['content'][:500]}")

        if not output:
            return "没有找到足够相关的笔记，换个关键词试试？"
        return "\n\n---\n\n".join(output)

    async def _arun(self, query: str) -> str:
        return self._run(query)
