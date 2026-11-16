"""三层配置：通用默认值 → 模式默认值 → 实例配置。"""
from pathlib import Path

import pytest
import yaml

from src.core.config import layers

ROOT = Path(__file__).resolve().parents[2]


def _home(tmp_path, local: dict | None) -> Path:
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    if local is not None:
        (home / "config" / "config.local.yaml").write_text(yaml.safe_dump(local, allow_unicode=True))
    return home


def test_personal_defaults_from_mode_file(tmp_path):
    cfg, mode, warnings = layers.load_layers(ROOT, _home(tmp_path, {"instance": {"name": "张三"}}))
    assert mode == "personal"
    assert (cfg["server"]["host"], cfg["server"]["port"]) == ("127.0.0.1", 8700)
    assert cfg["remote"] == {"url": "", "timeout": 10}
    assert "database" not in cfg                       # team 专用配置不出现在个人服务里
    assert cfg["instance"] == {"name": "张三", "mode": "personal"}
    assert cfg["server"]["max_sessions"] == 100        # 通用默认值仍在
    assert warnings == []


def test_team_defaults_and_local_override(tmp_path):
    local = {"instance": {"mode": "team"}, "database": {"host": "db", "password": "x"}, "server": {"port": 9000}}
    cfg, mode, _ = layers.load_layers(ROOT, _home(tmp_path, local))
    assert mode == "team"
    assert (cfg["server"]["host"], cfg["server"]["port"]) == ("0.0.0.0", 9000)   # 只覆盖写出的项
    assert (cfg["database"]["host"], cfg["database"]["port"], cfg["database"]["read_timeout"]) == ("db", 3306, 15)
    assert "remote" not in cfg and "visibility" not in cfg


def test_env_mode_wins_and_warns_on_conflict(tmp_path):
    home = _home(tmp_path, {"instance": {"mode": "personal"}})
    cfg, mode, warnings = layers.load_layers(ROOT, home, env_mode="team")
    assert mode == "team" and cfg["instance"]["mode"] == "team"
    assert any("不一致" in w for w in warnings)
    _, mode, warnings = layers.load_layers(ROOT, home, env_mode="master")
    assert mode == "personal" and any("POLARIS_MODE" in w for w in warnings)


def test_invalid_or_missing_mode(tmp_path):
    _, mode, warnings = layers.load_layers(ROOT, _home(tmp_path, {"instance": {"mode": "master"}}))
    assert mode == "personal" and any("只能是 team 或 personal" in w for w in warnings)
    _, mode, warnings = layers.load_layers(ROOT, _home(tmp_path / "b", None))   # 没有 config.local.yaml
    assert mode == "personal" and warnings == []


def test_misplaced_and_deprecated_keys(tmp_path):
    local = {"database": {"enabled": True, "host": "db", "password": "p"}, "storage": {"profile_file": "x"}}
    _, _, warnings = layers.load_layers(ROOT, _home(tmp_path, local))
    text = "\n".join(warnings)
    assert "database.enabled 已不再使用" in text and "storage.profile_file 已不再使用" in text
    assert "个人服务不使用 database 配置" in text
    team = {"instance": {"mode": "team"}, "remote": {"url": "http://x"}, "visibility": {"default_scope": "private"}}
    _, _, warnings = layers.load_layers(ROOT, _home(tmp_path / "t", team))
    assert any(w.startswith("remote：") for w in warnings) and any(w.startswith("visibility：") for w in warnings)
    empty_remote = {"instance": {"mode": "team"}, "remote": {"url": ""}}
    _, _, warnings = layers.load_layers(ROOT, _home(tmp_path / "e", empty_remote))
    assert warnings == []                               # 空值不算放错位置


def test_bad_yaml_reports_file_without_content(tmp_path):
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "config.local.yaml").write_text("llm:\n  api_key: secret-value\n bad: [")
    with pytest.raises(ValueError) as e:
        layers.load_layers(ROOT, home)
    assert "config.local.yaml" in str(e.value) and "secret-value" not in str(e.value)


def test_shipped_files_are_consistent():
    """随代码提交的配置和示例：能解析，模式文件声明自己的模式，示例里的键都有默认值或属于实例配置。"""
    for name in ("config.yaml", "config.team.yaml", "config.personal.yaml", "config.local.yaml.example"):
        assert isinstance(layers.read_yaml(ROOT / "config" / name), dict), name
    assert layers.read_yaml(ROOT / "config/config.team.yaml")["instance"]["mode"] == "team"
    assert layers.read_yaml(ROOT / "config/config.personal.yaml")["instance"]["mode"] == "personal"
    base = layers.read_yaml(ROOT / "config/config.yaml")
    assert "database" not in base and "remote" not in base and "visibility" not in base
    # 示例默认是 personal 模式；team 专用段是注释，不会触发"放错模式"的提示
    example = layers.read_yaml(ROOT / "config/config.local.yaml.example")
    assert example["instance"]["mode"] == "personal" and "database" not in example
    assert layers.check_local("personal", example) == []


def test_legacy_local_config_still_read_with_warning(tmp_path):
    """旧版本把实例配置放在 data/：新位置没有文件时读旧文件并提示迁移；新位置有文件时以新位置为准。"""
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "data" / "config.local.yaml").write_text("instance:\n  name: 旧位置\n")
    cfg, _, warnings = layers.load_layers(ROOT, home)
    assert cfg["instance"]["name"] == "旧位置"
    assert any("旧位置" in w and "config/config.local.yaml" in w for w in warnings)
    (home / "config").mkdir()
    (home / "config" / "config.local.yaml").write_text("instance:\n  name: 新位置\n")
    cfg, _, warnings = layers.load_layers(ROOT, home)
    assert cfg["instance"]["name"] == "新位置" and not any("旧位置" in w for w in warnings)


def test_no_defaults_left_in_data_dir():
    """默认配置只在 config/：data/ 只放运行数据。"""
    for name in ("config.yaml", "config.team.yaml", "config.personal.yaml"):
        assert not (ROOT / "data" / name).exists(), name


def _leaves(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            yield from _leaves(v, key + ".")
        else:
            yield key, v


def test_shipped_config_keys_are_all_read_by_code():
    """随代码提交的配置里不能有代码不读的配置项（避免"改了不生效"的死配置）。"""
    # layers.py 里列着已废弃的键名，不算"读取"
    files = [p for p in (ROOT / "src").rglob("*.py") if p.name != "layers.py"]
    sources = "\n".join(p.read_text(encoding="utf-8") for p in files + [ROOT / "scripts/service.py", ROOT / "run.py"])
    # 按段整体读取、不是以完整键名出现在代码里的配置项
    dynamic = ("channels.",)                              # 渠道 loader 遍历整个 channels 段
    by_section = {"server.host", "server.port", "instance.mode"}   # 启停脚本 / 配置合并按段读取
    unused = []
    for name in ("config.yaml", "config.team.yaml", "config.personal.yaml", "config.local.yaml.example"):
        for key, _ in _leaves(layers.read_yaml(ROOT / "config" / name)):
            if key.startswith(dynamic) or key in by_section:
                continue
            if f'"{key}"' not in sources and f"'{key}'" not in sources:
                unused.append(f"{name}: {key}")
    assert unused == []


def test_shipped_config_has_no_secret_values():
    """入库的默认值和示例里，密钥类配置项必须为空或明显的占位值。"""
    for name in ("config.yaml", "config.team.yaml", "config.personal.yaml"):
        for key, value in _leaves(layers.read_yaml(ROOT / "config" / name)):
            if any(s in key.lower() for s in ("api_key", "password", "secret", "token")):
                assert value in ("", None), f"{name}: {key}"


def test_mode_written_in_default_files_is_ignored_with_warning(tmp_path):
    """模式写在 config.yaml、或改了模式默认值文件里的 mode：不生效，并提示改错了地方。"""
    import shutil
    root = tmp_path / "proj"
    shutil.copytree(ROOT / "config", root / "config", ignore=shutil.ignore_patterns("config.local.yaml", "cli.yaml"))
    base = root / "config" / "config.yaml"
    base.write_text(base.read_text(encoding="utf-8").replace("instance:\n", 'instance:\n  mode: "team"\n', 1), encoding="utf-8")
    cfg, mode, warnings = layers.load_layers(root, _home(tmp_path, {"instance": {"name": "x"}}))
    assert mode == "personal" and cfg["instance"]["mode"] == "personal"
    assert any("config/config.yaml 里写了 instance.mode" in w for w in warnings)
    personal = root / "config" / "config.personal.yaml"
    personal.write_text(personal.read_text(encoding="utf-8").replace('mode: "personal"', 'mode: "team"'), encoding="utf-8")
    _, mode, warnings = layers.load_layers(root, _home(tmp_path / "b", None))
    assert mode == "personal" and any("config.personal.yaml 里的 instance.mode 被改成了 team" in w for w in warnings)
