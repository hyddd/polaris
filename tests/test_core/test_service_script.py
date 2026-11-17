"""启停脚本（scripts/service.py）：两种模式共用项目根目录时，启动记录互不干扰。"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("polaris_service_script", ROOT / "scripts" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return mod


def _state(home: Path, **data):
    (home / "logs").mkdir(parents=True, exist_ok=True)
    (home / "logs" / "polaris.service.json").write_text(json.dumps(data))


def test_both_modes_use_project_root(service, tmp_path):
    team, personal = service.Service("team"), service.Service("personal")
    assert team.home == personal.home == tmp_path.resolve()
    assert team.local_config == tmp_path.resolve() / "config" / "config.local.yaml"
    assert team.stop_cmd == "./stop-team.sh" and team.label != personal.label


def test_state_of_other_mode_is_ignored_and_kept(service, tmp_path):
    _state(tmp_path, mode="personal", backend="background", pid=12345, port=8700)
    team = service.Service("team")
    team.use_state = True
    assert team.read_state() == {}                    # 不会拿 personal 的端口、进程号
    assert team.port == 8710
    team.clear_state()
    assert (tmp_path / "logs" / "polaris.service.json").exists()    # 不会删掉 personal 的记录
    personal = service.Service("personal")
    assert personal.read_state()["pid"] == 12345
    personal.clear_state()
    assert not (tmp_path / "logs" / "polaris.service.json").exists()


def test_other_mode_running_detected(service, tmp_path, monkeypatch):
    _state(tmp_path, mode="personal", backend="background", pid=12345)
    monkeypatch.setenv("POLARIS_SERVICE_BACKEND", "background")
    monkeypatch.setattr(service.Background, "running_pid",
                        lambda self: 12345 if self.svc.read_state().get("pid") else None)
    other = service.Service("team").other_mode_running()
    assert other is not None and other.mode == "personal"
    assert service.Service("personal").other_mode_running() is None


def test_init_refuses_existing_config(service, tmp_path):
    team = service.Service("team")
    service.init_team(team)
    text = team.local_config.read_text(encoding="utf-8")
    assert "mode: team" in text and oct(team.local_config.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(SystemExit):
        service.init_team(team)
