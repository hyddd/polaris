"""公共库测试夹具。

需要真实 MySQL 的测试只在设置了 POLARIS_TEST_DB_HOST 等环境变量时运行（默认跳过，不碰任何远程库）：
  POLARIS_TEST_DB_HOST / _PORT / _USER / _PASSWORD / _NAME
每次测试用随机表前缀建表，结束后删除，不会碰正式的 polaris_ 表和库里其他表。
"""
import os
import uuid

import pytest

import src.core.db.scope as scope_mod
from src.core.config import config


def _env(name, default=None):
    return os.environ.get(f"POLARIS_TEST_DB_{name}", default)


requires_mysql = pytest.mark.skipif(not _env("HOST"), reason="未设置 POLARIS_TEST_DB_HOST，跳过真实 MySQL 测试")


@pytest.fixture
def mysql_db():
    """连真实 MySQL，但所有表名都换成随机临时表（polaris_t<随机>_<表名>），测完删除，不碰正式表。"""
    from src.core.db.mysql import Database
    from src.core.db.schema import ensure_schema, TABLES
    tag = f"polaris_t{uuid.uuid4().hex[:8]}_"

    class _TempTableDatabase(Database):
        def t(self, name: str) -> str:
            return f"`{tag}{name}`"

    db = _TempTableDatabase(_env("HOST"), int(_env("PORT", "3306")), _env("USER"), _env("PASSWORD", ""), _env("NAME"))
    ensure_schema(db)
    yield db
    for name in TABLES:
        db.execute(f"DROP TABLE IF EXISTS {db.t(name)}")
    db.close()


def set_mode(monkeypatch, mode: str, remote: str = "", db_host: str = "", default_scope: str = "public"):
    """切换服务模式（只改内存里的配置，测试结束自动还原）。"""
    monkeypatch.setitem(config._data, "instance", {"mode": mode, "name": f"测试{mode}"})
    monkeypatch.setitem(config._data, "remote", {"url": remote})
    monkeypatch.setitem(config._data, "database", {**config._data.get("database", {}), "host": db_host})
    monkeypatch.setitem(config._data, "visibility", {"default_scope": default_scope})


@pytest.fixture
def team_on(monkeypatch, mysql_db):
    """team 模式，公共库指向测试表。"""
    set_mode(monkeypatch, "team", db_host="test-host")
    monkeypatch.setattr(scope_mod, "_db", mysql_db)
    return mysql_db


@pytest.fixture
def personal_alone(monkeypatch):
    """personal 模式，没连团队服务：只有私人数据。"""
    set_mode(monkeypatch, "personal")
    monkeypatch.setattr(scope_mod, "_db", None)


@pytest.fixture
def personal_linked(monkeypatch):
    """personal 模式，配了团队服务地址（实际请求由测试注入的客户端处理）。"""
    set_mode(monkeypatch, "personal", remote="http://team.test")
    monkeypatch.setattr(scope_mod, "_db", None)


class FakeChroma:
    """本机 Chroma 的替身：按字符重合度打分，不发 embedding 请求。接口同 RAGVectorStore。"""

    def __init__(self):
        self.docs = {}      # id -> (filename, title, content, tags)

    def _score(self, query, text):
        return len(set(query) & set(text)) / max(len(set(query)), 1)

    def search(self, query, n_results=5):
        from src.domains.rag.models import RAGSearchResult
        hits = sorted(((self._score(query, v[2]), k, v) for k, v in self.docs.items()), reverse=True)
        return [RAGSearchResult(filename=v[0], title=v[1], content=v[2], score=round(s, 4), tags=v[3])
                for s, k, v in hits if s > 0][:n_results]

    def add_note(self, filename, title, content, tags):
        self.docs[f"note:{filename}"] = (filename, title, content, tags)

    def remove_note(self, filename):
        self.docs.pop(f"note:{filename}", None)

    def index_chunks(self, doc_id, chunks):
        for i, c in enumerate(chunks):
            fn = c.get("metadata", {}).get("filename", doc_id)
            self.docs[f"{doc_id}_{i}"] = (fn, fn, c["content"], [])

    def remove_chunks(self, doc_id):
        self.docs = {k: v for k, v in self.docs.items() if not k.startswith(f"{doc_id}_")}
