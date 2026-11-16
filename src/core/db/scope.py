"""服务模式（team / personal）、数据范围（public / private），以及公共库单例。

两种服务模式（instance.mode）：
- team：团队服务。只有公共数据：结构化数据存 MySQL，笔记/文档向量存服务器本地的 Chroma。
  不能创建私人数据。非技术 PM 直接用它的网页；personal 服务通过它的 HTTP 接口读写公共数据。
- personal（默认）：个人服务，装在每个人本机。私人数据存本机（JSON + Chroma）；
  配了 remote.url 时，公共数据通过 HTTP 调 team 服务；没配就是单人使用、只有私人数据。
  personal 服务从不连 MySQL。
"""
import logging
import threading

from src.core.config import config

logger = logging.getLogger("polaris.db")

TEAM = "team"
PERSONAL = "personal"
MODES = (TEAM, PERSONAL)
MODE_LABELS = {TEAM: "团队服务", PERSONAL: "个人服务"}

PUBLIC = "public"
PRIVATE = "private"
SCOPES = (PUBLIC, PRIVATE)
SCOPE_LABELS = {PUBLIC: "公共", PRIVATE: "私人"}

_db = None
_db_lock = threading.Lock()


class ScopeError(Exception):
    """要求的范围在当前服务模式下不可用（team 要私人、personal 没连团队服务却要公共）。"""


# 工具参数说明：让模型按用户的话决定存公共还是私有
SCOPE_FIELD_DESC = ("create 时的可见范围：public=公共（团队所有人可见），private=私人（只有自己可见，存本机）。"
                    "用户说「私人」「私有」「只给我」「个人的」时用 private；说「公共」「团队」「大家」时用 public；"
                    "没说就不传，使用系统默认")


def scope_tag(scope: str) -> str:
    """展示给用户的范围标签：【公共】/【私人】。系统提示词要求模型回答时原样保留。"""
    return f"【{SCOPE_LABELS.get(scope, scope)}】"


def public_unavailable_note(error: str | None) -> str:
    return f"\n（注意：团队服务暂时连不上，以上只有私人数据：{error}）" if error else ""


# --- 模式 ---

def instance_mode() -> str:
    mode = str(config.get("instance.mode", PERSONAL) or PERSONAL).strip().lower()
    if mode not in MODES:
        logger.error(f"instance.mode 只能是 team 或 personal：{mode!r}，按 personal 处理")
        return PERSONAL
    return mode


def is_team() -> bool:
    return instance_mode() == TEAM


def instance_name() -> str:
    return str(config.get("instance.name", "") or "").strip() or "Polaris"


def remote_url() -> str:
    return str(config.get("remote.url", "") or "").strip().rstrip("/")


def public_enabled() -> bool:
    """本服务能不能读写公共数据。team：配了数据库；personal：配了 remote.url。"""
    if is_team():
        return bool(config.get("database.host"))
    return bool(remote_url())


def private_enabled() -> bool:
    return not is_team()


def instance_info() -> dict:
    """给 /api/instance、TUI、网页展示用。"""
    mode = instance_mode()
    info = {"mode": mode, "mode_label": MODE_LABELS[mode], "name": instance_name(),
            "public": public_enabled(), "private": private_enabled()}
    if mode == PERSONAL:
        info["remote"] = remote_url() or None
    return info


# --- 公共库（只有 team 模式连 MySQL） ---

def get_database():
    """公共库单例；不是 team 模式或没配数据库时返回 None。首次获取时建表。"""
    global _db
    if not (is_team() and public_enabled()):
        return None
    if _db is None:
        with _db_lock:
            if _db is None:
                from .mysql import Database
                from .schema import ensure_schema
                db = Database(
                    host=config.get("database.host", ""),
                    port=config.get("database.port", 3306),
                    user=config.get("database.user", ""),
                    password=str(config.get("database.password", "")),
                    name=config.get("database.name", ""),
                    connect_timeout=config.get("database.connect_timeout", 5),
                    read_timeout=config.get("database.read_timeout", 15),
                )
                ensure_schema(db)
                logger.info(f"公共库已连接：{db.description}")
                _db = db
    return _db


def set_database(db) -> None:
    """测试用：替换公共库单例（None 表示清空）。"""
    global _db
    _db = db


# --- 范围 ---

def default_scope() -> str:
    if is_team():
        return PUBLIC
    if not public_enabled():
        return PRIVATE
    value = str(config.get("visibility.default_scope", PUBLIC)).lower()
    return value if value in SCOPES else PUBLIC


def resolve_scope(value: str | None) -> str:
    """把调用方给的 scope 规范化；None/空串用默认值。当前模式不支持的范围明确报错，不会悄悄换成另一种。"""
    if not value:
        return default_scope()
    v = str(value).strip().lower()
    aliases = {"公共": PUBLIC, "共享": PUBLIC, "团队": PUBLIC, "私人": PRIVATE, "私有": PRIVATE, "个人": PRIVATE}
    v = aliases.get(v, v)
    if v not in SCOPES:
        raise ScopeError(f"scope 只能是 public 或 private：{value!r}")
    if v == PRIVATE and is_team():
        raise ScopeError(f"这是团队服务（{instance_name()}），只保存公共数据，不能创建私人数据。"
                         f"需要私人数据的话，请在本机部署 Polaris（personal 模式）")
    if v == PUBLIC and not public_enabled():
        if is_team():
            raise ScopeError("团队服务没有配置数据库（database.host），无法保存公共数据")
        raise ScopeError("没有连接团队服务（remote.url 未配置），只能保存私人数据")
    return v
