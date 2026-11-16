"""公共库（MySQL）连接管理。

- 每个线程一条连接（PyMySQL 连接不能跨线程共用）；断线时重连并重试一次。
- 连接时强制 utf8mb4 和严格 sql_mode：服务端默认是 utf8 + 非严格模式，
  非严格模式下超长、非法的数据会被悄悄截断而不是报错。
- 表名前缀可配（默认无）；和其他项目共用一个库时设为 polaris_ 之类，避免冲突。
"""
import logging
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger("polaris.db")

STRICT_SQL_MODE = ("STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,"
                   "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION")
_RECONNECT_ERRORS = {2006, 2013, 2055}   # server gone away / lost connection


class DatabaseError(Exception):
    """公共库不可用或操作失败。message 面向用户。"""


class Database:
    def __init__(self, host: str, port: int, user: str, password: str, name: str,
                 connect_timeout: int = 5, read_timeout: int = 15):
        self._params = dict(host=host, port=int(port), user=user, password=password, database=name,
                            connect_timeout=connect_timeout, read_timeout=read_timeout,
                            write_timeout=read_timeout)
        self.description = f"{user}@{host}:{port}/{name}"
        self._local = threading.local()

    def t(self, name: str) -> str:
        """加反引号的表名。SQL 里的表名都经过这里（测试用它把表换成临时表）。"""
        return f"`{name}`"

    # --- 连接 ---

    def _connect(self):
        return pymysql.connect(**self._params, charset="utf8mb4", autocommit=True, cursorclass=DictCursor,
                               init_command=f"SET SESSION sql_mode='{STRICT_SQL_MODE}'")

    def _conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None or not conn.open:
            try:
                conn = self._connect()
            except pymysql.MySQLError as e:
                raise DatabaseError(f"连不上公共库 {self.description}：{e}") from e
            self._local.conn = conn
        return conn

    def _run(self, fn):
        for attempt in (1, 2):
            conn = self._conn()
            try:
                return fn(conn)
            except pymysql.OperationalError as e:
                if attempt == 1 and e.args and e.args[0] in _RECONNECT_ERRORS:
                    logger.warning(f"公共库连接断开，重连后重试：{e}")
                    self._local.conn = None
                    continue
                raise DatabaseError(f"公共库操作失败：{e}") from e
            except pymysql.MySQLError as e:
                raise DatabaseError(f"公共库操作失败：{e}") from e

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None and conn.open:
            conn.close()
        self._local.conn = None

    # --- 查询 ---

    def fetchall(self, sql: str, args=None) -> list[dict]:
        def go(conn):
            with conn.cursor() as c:
                c.execute(sql, args)
                return list(c.fetchall())
        return self._run(go)

    def fetchone(self, sql: str, args=None) -> dict | None:
        rows = self.fetchall(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args=None) -> int:
        """执行单条写语句，返回受影响行数。"""
        def go(conn):
            with conn.cursor() as c:
                return c.execute(sql, args)
        return self._run(go)

    def executemany(self, sql: str, rows: list) -> int:
        def go(conn):
            with conn.cursor() as c:
                return c.executemany(sql, rows)
        return self._run(go)

    @contextmanager
    def transaction(self):
        """事务：块内用 yield 出来的 cursor 执行；异常回滚。不做断线重试。"""
        conn = self._conn()
        try:
            conn.begin()
            with conn.cursor() as c:
                yield c
            conn.commit()
        except pymysql.MySQLError as e:
            conn.rollback()
            raise DatabaseError(f"公共库事务失败：{e}") from e
        except BaseException:
            conn.rollback()
            raise
