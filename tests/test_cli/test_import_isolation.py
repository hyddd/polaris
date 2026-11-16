"""--help 和参数错误路径不能加载服务端、不能起线程、不能写文件、不能发网络请求。"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import json, socket, sys, threading
calls = []
_orig = socket.socket.connect
def _connect(self, *a, **kw):
    calls.append(str(a))
    return _orig(self, *a, **kw)
socket.socket.connect = _connect
from src.cli.main import main
codes = [main(["--help"]), main(["todo", "--help"]), main(["-p", "a", "--stdin"])]
heavy = sorted(m for m in sys.modules if m.split(".")[0] in ("httpx", "rich", "prompt_toolkit", "langchain", "langgraph", "fastapi")
               or m.startswith(("src.agent", "src.server", "src.core", "src.domains", "src.session")))
print("@@" + json.dumps({"codes": codes, "heavy": heavy, "threads": threading.active_count(), "net": calls}))
"""


def test_help_has_no_side_effects(tmp_path):
    home = tmp_path / "cli-home"
    env = {**os.environ, "POLARIS_CLI_HOME": str(home), "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    line = next(x for x in proc.stdout.splitlines() if x.startswith("@@"))
    result = json.loads(line[2:])
    assert result["codes"] == [0, 0, 2]
    assert result["heavy"] == []          # 没加载服务端模块和重依赖
    assert result["threads"] == 1        # 没起后台线程
    assert result["net"] == []           # 没有网络连接
    assert not home.exists()             # 没写任何本地文件
