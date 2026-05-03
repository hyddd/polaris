import importlib
import logging
import threading
from pathlib import Path
from langchain_core.tools import BaseTool
from typing import Optional

logger = logging.getLogger("polaris.tools")


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def discover_and_register(self) -> None:
        """Auto-discover tools by scanning tools/*/ subdirectories.

        Each tool subdirectory must expose a ``create_default()`` factory function
        that returns a fully-configured BaseTool instance.  If the function
        is absent, the subdirectory is skipped (useful for helper-only modules).
        """
        import src.tools as tools_pkg

        tools_path = Path(tools_pkg.__path__[0])

        # 遍历 src/tools/ 下的子目录
        for item in sorted(tools_path.iterdir()):
            if not item.is_dir():
                continue
            if item.name.startswith('_') or item.name == 'registry':
                continue

            try:
                mod = importlib.import_module(f"src.tools.{item.name}")
                factory = getattr(mod, "create_default", None)
                if factory is None:
                    continue
                tool = factory()
                if isinstance(tool, BaseTool):
                    self.register(tool)
                    logger.info(f"[{tool.name}] 已注册 (from {item.name})")
                else:
                    logger.warning(f"{item.name}.create_default() 未返回 BaseTool 实例")
            except Exception as e:
                logger.warning(f"加载工具模块 {item.name} 失败: {e}")

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
