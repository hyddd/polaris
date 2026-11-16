"""RAG — 数据模型。"""

from dataclasses import dataclass, field


@dataclass
class RAGSearchResult:
    filename: str
    title: str
    content: str
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    scope: str = "private"   # 本机 Chroma 的结果是 local_scope；personal 从团队服务查到的是 public

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "tags": self.tags,
            "scope": self.scope,
        }
