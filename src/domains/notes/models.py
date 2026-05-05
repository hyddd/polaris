"""Note — 笔记数据模型。"""

from dataclasses import dataclass, field


@dataclass
class Note:
    filename: str      # "my-note.md"
    title: str
    content: str       # 正文（不含 frontmatter）
    tags: list[str] = field(default_factory=list)
    date: str = ""     # "YYYY-MM-DD"
    path: str = ""     # 完整路径

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "date": self.date,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            filename=data.get("filename", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            date=data.get("date", ""),
            path=data.get("path", ""),
        )


@dataclass
class SearchResult:
    filename: str
    title: str
    content: str
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "tags": self.tags,
        }
