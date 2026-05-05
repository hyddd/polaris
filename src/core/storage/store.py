"""Data storage protocol and JSON file implementation."""
from typing import Protocol, runtime_checkable
from pathlib import Path
import json

from src.core.storage.atomic import _atomic_write


@runtime_checkable
class DataStore(Protocol):
    """数据存储协议"""

    def load(self) -> dict | list:
        """读取所有数据"""
        ...

    def save(self, data: dict | list) -> None:
        """写入所有数据"""
        ...


class JsonFileStore:
    """JSON 文件存储实现"""

    def __init__(self, file_path: str | Path):
        self._path = Path(file_path)

    def load(self) -> dict | list:
        """读取 JSON 文件，文件不存在返回空列表"""
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return raw
        return []

    def save(self, data: dict | list) -> None:
        """写入 JSON 文件（使用原子写入保障）"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path, content)
