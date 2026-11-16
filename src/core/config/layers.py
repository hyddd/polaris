"""三层配置的合并规则（不依赖项目其他模块，启停脚本也直接加载这个文件）。

配置和数据分开存放：配置在 config/，运行数据在 data/。

加载顺序，后加载的按配置项逐项覆盖先加载的：
  1. <项目>/config/config.yaml                通用默认值
  2. <项目>/config/config.<模式>.yaml          模式默认值：config.team.yaml / config.personal.yaml
  3. <实例目录>/config/config.local.yaml       本实例的设置（不提交到 git）

旧版本把实例配置放在 <实例目录>/data/config.local.yaml：新位置没有文件时仍读取旧位置，并提示迁移。

运行模式：环境变量 POLARIS_MODE（启停脚本设置）> config.local.yaml 的 instance.mode > personal。
"""
from pathlib import Path

import yaml

MODES = ("team", "personal")
DEFAULT_MODE = "personal"
CONFIG_DIR = "config"
LOCAL_FILE = "config.local.yaml"


def local_config_path(home: Path) -> tuple[Path, bool]:
    """实例配置文件的位置，返回 (路径, 是否旧位置)。新位置不存在、旧位置存在时用旧位置。"""
    new = Path(home) / CONFIG_DIR / LOCAL_FILE
    legacy = Path(home) / "data" / LOCAL_FILE
    if not new.exists() and legacy.is_file():
        return legacy, True
    return new, False


def legacy_warning(path: Path, home: Path) -> str:
    return (f"实例配置仍在旧位置 {path}，请移到 {Path(home) / CONFIG_DIR / LOCAL_FILE}"
            f"（配置和数据已分开存放：配置在 config/，数据在 data/）")

# 已不再使用的配置项：出现在 config.local.yaml 里时提示可以删除
DEPRECATED_KEYS = {
    "database.enabled": "团队服务是否有公共数据看 database.host，个人服务看 remote.url",
    "database.sync_interval_seconds": "已改为 sync.interval_seconds",
    "vector.memory_warn_mb": "公共向量已改存团队服务的 Chroma",
    "reminders.check_interval": "提醒由调度器按时触发，不再轮询",
    "cleanup.archive_dir": "归档功能未实现",
    "cleanup.archive_max_age_days": "归档功能未实现",
    "cleanup.calendar_retention_days": "代码中没有读取，固定清理 14 天前的私人日程",
    "cleanup.todos_retention_days": "代码中没有读取，固定清理截止日期在 30 天前的已完成私人待办",
    "storage.profile_file": "代码中没有读取",
    "admin.enabled": "代码中没有读取，网页端始终启用",
    "llm.temperature": "代码中没有读取：对话固定 0.3，上下文压缩固定 0",
    "llm.max_tokens": "代码中没有读取：输出长度使用模型默认值",
    "llm.use_responses_api": "已移除",
    "tools.calendar": "代码中没有读取",
    "database.table_prefix": "表名前缀功能已移除，表名固定不加前缀；如果原来设置过前缀，需先把表改回无前缀的名字（RENAME TABLE）",
}

# 只在某一种模式下生效的配置项：出现在另一种模式的 config.local.yaml 里时提示
MODE_ONLY_KEYS = {
    "team": {
        "database": "个人服务不使用 database 配置（公共数据通过 remote.url 访问团队服务），"
                    "建议从个人服务的配置中删除，避免数据库密码扩散",
    },
    "personal": {
        "remote": "团队服务不使用 remote 配置，将被忽略",
        "visibility": "团队服务只保存公共数据，visibility 配置将被忽略",
    },
}


def read_yaml(path: Path) -> dict:
    """读取 YAML 文件；不存在时返回空字典，格式错误时抛 ValueError（不包含文件内容）。"""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"（第 {mark.line + 1} 行附近）" if mark is not None else ""
        raise ValueError(f"配置文件无法解析，请检查 YAML 格式：{path}{where}")
    if not isinstance(data, dict):
        raise ValueError(f"配置文件的顶层必须是 YAML 对象：{path}")
    return data


def deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def local_mode(local: dict) -> str:
    """config.local.yaml 里写的 instance.mode（原样小写，没写为空串）。"""
    instance = local.get("instance") if isinstance(local.get("instance"), dict) else {}
    return str(instance.get("mode") or "").strip().lower()


def resolve_mode(local: dict, env_mode: str = "") -> tuple[str, list[str]]:
    """返回 (运行模式, 提示)。"""
    warnings = []
    env_mode = (env_mode or "").strip().lower()
    written = local_mode(local)
    if env_mode:
        if env_mode not in MODES:
            warnings.append(f"环境变量 POLARIS_MODE 只能是 team 或 personal：{env_mode!r}，已忽略")
        else:
            if written and written != env_mode:
                warnings.append(f"环境变量 POLARIS_MODE={env_mode} 和 config.local.yaml 的 instance.mode={written} 不一致，"
                                f"按 {env_mode} 运行")
            return env_mode, warnings
    if written and written not in MODES:
        warnings.append(f"instance.mode 只能是 team 或 personal：{written!r}，按 {DEFAULT_MODE} 运行")
        return DEFAULT_MODE, warnings
    return written or DEFAULT_MODE, warnings


def _get(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _has_value(value) -> bool:
    if isinstance(value, dict):
        return any(_has_value(v) for v in value.values())
    return value not in (None, "", [], {})


def check_local(mode: str, local: dict) -> list[str]:
    """检查 config.local.yaml 里放错模式或已废弃的配置项。"""
    warnings = []
    for key, reason in DEPRECATED_KEYS.items():
        if _get(local, key) is not None:
            warnings.append(f"{key} 已不再使用（{reason}），可以从 config.local.yaml 中删除")
    for owner, keys in MODE_ONLY_KEYS.items():
        if owner == mode:
            continue
        for key, reason in keys.items():
            value = _get(local, key)
            if value is not None and _has_value(value):
                warnings.append(f"{key}：{reason}")
    return warnings


def load_layers(project_root: Path, home: Path, env_mode: str = "",
                local_file: Path | None = None) -> tuple[dict, str, list[str]]:
    """按三层合并配置，返回 (配置, 运行模式, 提示)。instance.mode 会被设为实际运行的模式。

    local_file 默认按 local_config_path(home) 确定。
    """
    defaults_dir = Path(project_root) / CONFIG_DIR
    warnings = []
    if local_file is None:
        local_file, legacy = local_config_path(home)
        if legacy:
            warnings.append(legacy_warning(local_file, home))
    local = read_yaml(Path(local_file))
    mode, mode_warnings = resolve_mode(local, env_mode)
    warnings += mode_warnings
    base, mode_defaults = read_yaml(defaults_dir / "config.yaml"), read_yaml(defaults_dir / f"config.{mode}.yaml")
    # 运行模式只能由启停脚本或 config.local.yaml 决定；默认值文件里的 mode 改了也不生效，提示改错了地方
    if local_mode({"instance": base.get("instance")}):
        warnings.append("config/config.yaml 里写了 instance.mode，不会生效：运行模式只能写在实例的 config.local.yaml")
    written = local_mode({"instance": mode_defaults.get("instance")})
    if written and written != mode:
        warnings.append(f"config/config.{mode}.yaml 里的 instance.mode 被改成了 {written}，不会生效："
                        f"运行模式只能写在实例的 config.local.yaml")
    merged = deep_merge(base, mode_defaults)
    deep_merge(merged, local)
    merged.setdefault("instance", {})
    if not isinstance(merged["instance"], dict):
        merged["instance"] = {}
    merged["instance"]["mode"] = mode
    return merged, mode, warnings + check_local(mode, local)
