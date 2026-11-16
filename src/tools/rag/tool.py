from typing import Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.core.db import SCOPE_FIELD_DESC, scope_tag


def create_default() -> "RAGSearchTool":
    """Factory for auto-discovery. Creates a RAGSearchTool with default config."""
    from src.core.config import config
    return RAGSearchTool(
        persist_dir=str(config.resolve_path(config.get("storage.vector_db_dir", "data/chroma"))),
        collection_name="notes",
    )


class RAGInput(BaseModel):
    action: Literal["search", "upload", "list", "delete"] = Field(
        default="search",
        description="操作类型：search=搜索知识库，upload=上传文档，list=列出文档，delete=删除文档"
    )
    query: Optional[str] = Field(default=None, description="search 时的搜索关键词")
    file_path: Optional[str] = Field(default=None, description="upload 时的文件路径")
    doc_id: Optional[str] = Field(default=None, description="delete 时的文档 ID")
    scope: Optional[Literal["public", "private"]] = Field(
        default=None, description=SCOPE_FIELD_DESC.replace("create 时", "upload 时"))


class RAGSearchTool(BaseTool):
    name: str = "rag_search"
    description: str = "搜索用户的知识库和所有笔记。支持搜索、上传文档、列出文档、删除文档。"
    args_schema: type[BaseModel] = RAGInput
    persist_dir: str = ""
    collection_name: str = "notes"

    def _run(self, action: str = "search", query: str = None,
             file_path: str = None, doc_id: str = None, scope: str = None) -> str:
        from src.core.db import ScopeError, DatabaseError
        try:
            return self._dispatch(action, query, file_path, doc_id, scope)
        except (ScopeError, DatabaseError) as e:
            return f"操作失败：{e}"

    def _dispatch(self, action, query, file_path, doc_id, scope) -> str:
        from src.domains.rag import get_rag_domain

        domain = get_rag_domain()
        if not domain:
            return "检索服务未就绪，请稍后重试。"

        if action == "search":
            return self._do_search(domain, query)
        elif action == "upload":
            return self._do_upload(domain, file_path, scope)
        elif action == "list":
            return self._do_list(domain)
        elif action == "delete":
            return self._do_delete(domain, doc_id)
        else:
            return f"未知操作: {action}"

    def _do_search(self, domain, query: str) -> str:
        """执行搜索。"""
        if not query or not query.strip():
            return "请输入搜索内容。"

        results = domain.search(query.strip(), top_k=5)
        if not results:
            return "没有找到相关笔记。"

        output = []
        for r in results:
            if r.score < 0.3:
                continue
            title = r.title or "未命名"
            output.append(f"## {scope_tag(r.scope)} {title} (相关度: {r.score:.0%})\n{r.content[:500]}")

        if not output:
            return "没有找到足够相关的笔记，换个关键词试试？"
        return "\n\n---\n\n".join(output)

    def _do_upload(self, domain, file_path: str, scope: str = None) -> str:
        """上传文档。"""
        if not file_path:
            return "请提供文件路径。"

        result = domain.upload_document(file_path=file_path, scope=scope)
        if not result:
            return "文档解析失败，请检查文件格式。"

        return (f"文档已上传并索引{scope_tag(result.get('scope', 'private'))}：\n"
                f"- 文件名：{result['filename']}\n"
                f"- 文档 ID：{result['doc_id']}\n"
                f"- 分块数：{result['chunk_count']}")

    def _do_list(self, domain) -> str:
        """列出文档。"""
        docs = domain.list_documents()
        if not docs:
            return "知识库中暂无文档。"

        output = ["知识库文档列表："]
        for doc in docs:
            tags = ", ".join(doc.get("tags", [])) or "无标签"
            output.append(f"- {scope_tag(doc.get('scope', 'private'))} {doc['filename']} (ID: {doc['doc_id']}, 分块: {doc['chunk_count']}, 标签: {tags})")
        return "\n".join(output)

    def _do_delete(self, domain, doc_id: str) -> str:
        """删除文档。"""
        if not doc_id:
            return "请提供文档 ID。"

        if domain.delete_document(doc_id):
            return f"文档已删除：{doc_id}"
        return f"文档不存在：{doc_id}"

    async def _arun(self, action: str = "search", query: str = None,
                    file_path: str = None, doc_id: str = None, scope: str = None) -> str:
        return self._run(action, query, file_path, doc_id, scope)
