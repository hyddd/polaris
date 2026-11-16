"""Application configuration — loaded from YAML files.

配置在 config/，运行数据在 data/。三层配置，后加载的按配置项逐项覆盖先加载的（规则见 layers.py）：
  1. config/config.yaml                       通用默认值（随代码提交）
  2. config/config.<模式>.yaml                 模式默认值：config.team.yaml / config.personal.yaml（随代码提交）
  3. <POLARIS_HOME>/config/config.local.yaml   本实例的设置（gitignore，放密钥）

Usage:
    from src.core.config import config

    model = config.get("llm.model", "gpt-4o")
    path = config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))
"""

import logging
import os
from pathlib import Path

from . import layers

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 多实例部署：POLARIS_HOME 指向实例目录（其下 config/ 放实例配置，data/ 放运行数据）
_HOME = Path(os.environ.get("POLARIS_HOME", PROJECT_ROOT))

# 网页"配置"页修改配置时写入的文件；仍在旧位置（data/）时写旧文件，避免出现两份
_LOCAL_CONFIG_FILE = layers.local_config_path(_HOME)[0]


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


class Config:
    """Configuration manager — loads from YAML, supports dot-separated access."""

    def __init__(self):
        self._data: dict = {}
        self.mode: str = layers.DEFAULT_MODE
        self.warnings: list[str] = []     # 放错模式、已废弃的配置项等，服务启动时写进日志

    def load(self) -> None:
        """Load (or reload) configuration from YAML files."""
        try:
            self._data, self.mode, self.warnings = layers.load_layers(
                PROJECT_ROOT, _HOME, os.environ.get("POLARIS_MODE", ""), local_file=_LOCAL_CONFIG_FILE)
        except ValueError as e:
            logging.getLogger("polaris.config").error(str(e))
            raise
        # 校验（仅在有 llm 配置时，避免测试环境报错）
        if "llm" in self._data:
            from .schema import AppConfig
            try:
                AppConfig(**self._data)
            except Exception as e:
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
