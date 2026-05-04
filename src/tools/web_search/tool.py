from typing import Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "WebSearchTool":
    """Factory for auto-discovery."""
    return WebSearchTool()


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")
    num_results: int = Field(default=3, description="返回结果数量，默认 3")


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "搜索互联网获取实时信息。适用于查天气、新闻、事实等。"
    args_schema: type[BaseModel] = WebSearchInput
    api_key: str = ""
    api_base: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._refresh_config()
        from src.core.events import event_bus
        event_bus.subscribe("config:reload", lambda **kw: self._refresh_config())

    def _refresh_config(self):
        from src.core.config import config
        self.api_key = config.get("tools.web_search.api_key", "")
        self.api_base = config.get("tools.web_search.api_base", "https://api.tavily.com")

    def _run(self, query: str, num_results: int = 3) -> str:
        if not self.api_key:
            return "搜索功能未配置。请在 config.yaml 中设置 tools.web_search.api_key。"

        try:
            import httpx
            response = httpx.post(
                f"{self.api_base}/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": num_results,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                return f"没有找到关于「{query}」的搜索结果。"

            lines = [f"搜索「{query}」的结果：\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", "")[:200]
                lines.append(f"{i}. **{title}**")
                lines.append(f"   {snippet}")
                lines.append(f"   链接：{url}\n")

            return "\n".join(lines)

        except Exception as e:
            return f"搜索失败：{e}"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
