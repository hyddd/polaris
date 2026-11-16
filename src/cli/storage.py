"""客户端本地状态：只存连接相关的 UI 状态（上次用的会话），不存聊天内容或业务数据。

目录权限 700、文件 600。状态文件损坏时改名保留（*.corrupt-<时间>），按空状态继续，不自动清空目录。
"""
import json
import os
import tempfile
import time
from pathlib import Path


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def write_private(path: Path, content: str) -> None:
    """原子写入，结果文件权限 600。"""
    ensure_private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class StateStore:
    def __init__(self, path: Path, key: str):
        self.path = path
        self.key = key
        self.warning: str | None = None
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "profiles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
                raise ValueError("结构不对")
            return data
        except (OSError, ValueError) as e:
            backup = self.path.with_name(f"{self.path.name}.corrupt-{time.strftime('%Y%m%d%H%M%S')}")
            try:
                self.path.rename(backup)
                self.warning = f"本地状态文件损坏（{e}），已改名保留为 {backup.name}，按空状态继续"
            except OSError:
                self.warning = f"本地状态文件损坏（{e}），按空状态继续"
            return {"version": 1, "profiles": {}}

    @property
    def last_session(self) -> str | None:
        return self._data["profiles"].get(self.key, {}).get("last_session")

    def set_last_session(self, session_id: str) -> None:
        self._data["profiles"].setdefault(self.key, {})["last_session"] = session_id
        write_private(self.path, json.dumps(self._data, ensure_ascii=False, indent=2))
