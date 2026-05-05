"""Application configuration — loaded from YAML files.

Default: data/config.yaml (tracked in git)
Override: data/config.local.yaml (gitignored, for local secrets)

Usage:
    from src.core.config import config

    model = config.get("llm.model", "gpt-4o")
    path = config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))
"""

import yaml
from pathlib import Path

import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 多实例部署：POLARIS_HOME 指向独立数据目录
_HOME = Path(os.environ.get("POLARIS_HOME", PROJECT_ROOT))
_DATA_DIR = _HOME / "data"

_CONFIG_FILE = PROJECT_ROOT / "data/config.yaml"
_LOCAL_CONFIG_FILE = _DATA_DIR / "config.local.yaml"

def _coerce(value):
    """将字符串转为合适的类型：bool / int / float / str。"""
    if not isinstance(value, str):
        return value
    v = value.lower()
    if v == "true":
        return True
    if v == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base dict."""
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def _load_yaml_config() -> dict:
    """Load config from YAML files (default + local override)."""
    config = {}
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            config = yaml.safe_load(f) or {}
    if _LOCAL_CONFIG_FILE.exists():
        with open(_LOCAL_CONFIG_FILE) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    return config


class Config:
    """Configuration manager — loads from YAML, supports dot-separated access."""

    def __init__(self):
        self._data: dict = {}

    def load(self) -> None:
        """Load (or reload) configuration from YAML files."""
        self._data = _load_yaml_config()
        # 校验（仅在有 llm 配置时，避免测试环境报错）
        if "llm" in self._data:
            from .schema import AppConfig
            try:
                AppConfig(**self._data)
            except Exception as e:
                import logging
                logging.getLogger("polaris.config").warning(f"配置校验警告: {e}")

    def as_dict(self) -> dict:
        """Return the full config as a dict (read-only snapshot)."""
        return dict(self._data)

    def get(self, key: str, default=None):
        """Get a value from config using dot-separated key path."""
        keys = key.split(".")
        val = self._data
        for k in keys:
            if not isinstance(val, dict) or k not in val:
                return default
            val = val[k]
        return val

    def resolve_path(self, val: str) -> Path:
        """Resolve a relative path against the data home directory."""
        p = Path(val)
        if p.is_absolute():
            return p
        return _HOME / p

    def set(self, key: str, value: str) -> None:
        """Persist a config value to config.local.yaml (overrides default)."""
        import yaml

        local_data = {}
        if _LOCAL_CONFIG_FILE.exists():
            local_data = yaml.safe_load(
                _LOCAL_CONFIG_FILE.read_text(encoding="utf-8")
            ) or {}

        keys = key.split(".")
        d = local_data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = _coerce(value)

        _LOCAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_CONFIG_FILE.write_text(
            yaml.dump(local_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def remove(self, key: str) -> None:
        """Remove a config key from config.local.yaml."""
        import yaml

        if not _LOCAL_CONFIG_FILE.exists():
            return
        local_data = yaml.safe_load(
            _LOCAL_CONFIG_FILE.read_text(encoding="utf-8")
        ) or {}
        keys = key.split(".")
        d = local_data
        for k in keys[:-1]:
            if k not in d:
                return
            d = d[k]
        if keys[-1] in d:
            del d[keys[-1]]
        _LOCAL_CONFIG_FILE.write_text(
            yaml.dump(local_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def reload(self) -> dict:
        """Re-read YAML config files, publish config:reload event.

        Returns the full config snapshot dict.
        """
        self.load()
        from src.core.infra import event_bus
        event_bus.publish("config:reload")
        return dict(self._data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
config = Config()
config.load()
