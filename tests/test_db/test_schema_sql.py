"""deploy/mysql/schema.sql 必须与代码中的表定义（src/core/db/schema.py）一致。

schema.sql 是从数据库导出的（SHOW CREATE TABLE），写法和代码不同：MySQL 会补上显示宽度（INT(10)）、
给默认值加引号（DEFAULT '0'）、省略 NULL。这里把两边规范化后逐表、逐列、逐索引比较，不需要连数据库。
"""
import re
from pathlib import Path

from src.core.db.schema import ddl

ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "deploy" / "mysql" / "schema.sql"


def _normalize_type(definition: str) -> str:
    d = re.sub(r"COMMENT\s+'[^']*'", " ", definition, flags=re.I)
    d = re.sub(r"COLLATE\s+\w+|CHARACTER SET\s+\w+", " ", d, flags=re.I)
    d = re.sub(r"\b(SMALLINT|MEDIUMINT|INT|BIGINT)\(\d+\)", r"\1", d, flags=re.I)   # 显示宽度（TINYINT(1) 保留）
    d = re.sub(r"DEFAULT\s+'(-?\d+(?:\.\d+)?)'", r"DEFAULT \1", d, flags=re.I)        # DEFAULT '0' → DEFAULT 0
    d = re.sub(r"\bDEFAULT\s+NULL\b", " ", d, flags=re.I)                             # 可空列的 DEFAULT NULL 是默认行为
    d = re.sub(r"(?<!NOT)\s+NULL\b", " ", " " + d, flags=re.I)                          # 单独的 NULL 是默认行为
    return re.sub(r"\s+", " ", d).strip().upper()


def _parse(statement: str) -> tuple[str, dict, list]:
    name = re.search(r"CREATE TABLE(?: IF NOT EXISTS)?\s+`(\w+)`", statement, re.I).group(1)
    body = statement[statement.index("(") + 1: statement.rindex(")")]
    # 按顶层逗号切分（ENUM('a','b') 里的逗号不切）
    parts, depth, buf = [], 0, ""
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(buf); buf = ""
        else:
            buf += ch
    parts.append(buf)
    columns, keys = {}, []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        if re.match(r"(PRIMARY KEY|KEY|UNIQUE|INDEX)\b", part, re.I):
            keys.append(re.sub(r"[`\s]", "", part).upper())
        else:
            m = re.match(r"`?(\w+)`?\s+(.*)", part, re.S)
            columns[m.group(1)] = _normalize_type(m.group(2))
    return name, columns, sorted(keys)


def test_schema_sql_matches_code():
    text = SQL_FILE.read_text(encoding="utf-8")
    from_file = {n: (c, k) for n, c, k in (_parse(s) for s in re.split(r"(?m)(?=^CREATE TABLE)", text) if s.startswith("CREATE"))}
    from_code = {n: (c, k) for n, c, k in (_parse(s) for s in ddl())}
    assert sorted(from_file) == sorted(from_code), "表不一致"
    for table, (code_cols, code_keys) in from_code.items():
        file_cols, file_keys = from_file[table]
        assert list(file_cols) == list(code_cols), f"{table} 的列（含顺序）不一致"
        for col, typ in code_cols.items():
            assert file_cols[col] == typ, f"{table}.{col}：代码 {typ!r}，schema.sql {file_cols[col]!r}"
        assert file_keys == code_keys, f"{table} 的主键/索引不一致"


def test_schema_sql_has_no_real_connection_info():
    """公开仓库：文件里不能出现数据、账号、密码。"""
    text = SQL_FILE.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\b|\bIDENTIFIED\s+BY\b|\bPASSWORD\b", text, re.I)
