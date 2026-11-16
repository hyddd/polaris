"""Domains — 领域层模块。"""

# 导入所有 Domain 模块，确保模块级的 event_bus.subscribe 执行
from src.core import db  # noqa: F401  公共库：app:startup 时连接并启动定期同步（public:sync）
from . import calendar
from . import todos
from . import notes
from . import persona
from . import scheduler
from . import reminder
from . import rag
from . import voice
