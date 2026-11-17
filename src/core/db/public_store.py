"""公共存储的公共部分：取公共库、JSON 数组列、合并读时的容错。"""
import json
import logging
from datetime import date, datetime

from .mysql import DatabaseError
from .scope import get_database

logger = logging.getLogger("polaris.db")


class PublicStoreBase:
    """公共存储基类。每次操作现取公共库：启动时连不上，之后恢复了也能用。"""

    def __init__(self, db_getter=get_database):
        self._db_getter = db_getter

    def db(self):
        db = self._db_getter()
        if db is None:
            raise DatabaseError("公共库未启用")
        return db


def dump_list(values) -> str:
    return json.dumps(list(values or []), ensure_ascii=False)


def load_list(raw) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def date_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def now() -> datetime:
    return datetime.now()


class MergedReadMixin:
    """组合存储（私有 + 公共）的读容错：公共数据读不到时（team 服务或数据库连不上）只返回私人数据，并记下原因。"""

    public_error: str | None = None

    def _public_read(self, fn, default):
        if self._public is None:
            return default
        try:
            result = fn()
            self.public_error = None
            return result
        except DatabaseError as e:
            self.public_error = str(e)
            logger.warning(f"公共数据读取失败，只显示私人数据：{e}")
            return default


def _force_private(value):
    if isinstance(value, list):
        return [_force_private(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_force_private(v) for v in value)
    if hasattr(value, "scope"):
        value.scope = "private"
    return value


class PrivateOnly:
    """包住本机的私人存储：读出来的数据一律标为私人。

    本机文件里存的只能是私人数据；历史上曾有修改操作把文件里的 scope 改成了 public（数据并没有挪到公共库），
    这里统一纠正，避免把私人数据显示成【公共】。
    """

    def __init__(self, store):
        self._store = store

    def __getattr__(self, name):
        attr = getattr(self._store, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            return _force_private(attr(*args, **kwargs))
        return call


class NoPrivate:
    """team 模式没有私人数据：组合存储的私人一侧用它占位。

    读操作返回空（list/search/find → []，get → None），清理返回 0；
    写私人数据在 resolve_scope 那一步就被拒绝了，走不到这里。
    """

    def __getattr__(self, name):
        if name.startswith(("list", "search", "find")):
            return lambda *a, **kw: []
        if name == "cleanup":
            return lambda *a, **kw: 0
        return lambda *a, **kw: None
