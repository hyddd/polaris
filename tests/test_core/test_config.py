"""Tests for src.core.config.Config."""

import sys
import yaml
from pathlib import Path

from src.core.config import Config  # triggers package load, populates sys.modules
config_mod = sys.modules["src.core.config.config"]


def test_get_nested_key():
    cfg = Config()
    cfg._data = {"llm": {"model": "gpt-4o", "temperature": 0.7}}
    assert cfg.get("llm.model") == "gpt-4o"
    assert cfg.get("llm.temperature") == 0.7


def test_get_default():
    cfg = Config()
    cfg._data = {"llm": {"model": "gpt-4o"}}
    assert cfg.get("llm.missing", "fallback") == "fallback"
    assert cfg.get("nonexistent.key") is None


def test_set_and_get(tmp_path, monkeypatch):
    local_file = tmp_path / "config.local.yaml"
    monkeypatch.setattr(config_mod, "_LOCAL_CONFIG_FILE", local_file)

    cfg = Config()
    cfg.set("my.key", "hello")

    # 文件应该写入了
    assert local_file.exists()
    data = yaml.safe_load(local_file.read_text(encoding="utf-8"))
    assert data == {"my": {"key": "hello"}}

    # 重新 load 后 get 能取到
    cfg.load()
    assert cfg.get("my.key") == "hello"


def test_remove(tmp_path, monkeypatch):
    local_file = tmp_path / "config.local.yaml"
    monkeypatch.setattr(config_mod, "_LOCAL_CONFIG_FILE", local_file)

    cfg = Config()
    cfg.set("keep", "yes")
    cfg.set("drop", "no")
    cfg.remove("drop")

    data = yaml.safe_load(local_file.read_text(encoding="utf-8"))
    assert "drop" not in data
    assert data["keep"] == "yes"


def test_resolve_path_relative(monkeypatch):
    fake_home = Path("/fake/home")
    monkeypatch.setattr(config_mod, "_HOME", fake_home)

    cfg = Config()
    assert cfg.resolve_path("data/file.json") == fake_home / "data/file.json"


def test_resolve_path_absolute():
    cfg = Config()
    assert cfg.resolve_path("/abs/path/file.json") == Path("/abs/path/file.json")
