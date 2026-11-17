"""Polaris 服务启停。由 start-team.sh / stop-team.sh / start-personal.sh / stop-personal.sh 调用。

- personal（个人服务）：实例目录是项目根目录（config/、data/、logs/），只监听 127.0.0.1，默认端口 8700。
- team（团队服务）：实例目录默认 instances/team（--home 或环境变量 POLARIS_TEAM_HOME 可改），
  默认监听 0.0.0.0:8710，让别人的个人服务和网页能连上。两种服务可以在同一台机器上同时运行。
- 实例目录下：config/ 放实例配置，data/ 放运行数据，logs/ 放日志。
- 配置按三层合并：config/config.yaml → config/config.<模式>.yaml → <实例目录>/config/config.local.yaml
  （规则见 src/core/config/layers.py，与服务端完全一致）。端口和监听地址取 server.port / server.host。
- 启动的服务进程带环境变量 POLARIS_MODE=<模式>，保证按脚本对应的模式加载配置。

- macOS：用 launchd 用户级服务托管（不放进登录自启目录）；
  其他系统：后台进程 + 状态文件，不会开机自启、崩溃也不会自动拉起，正式部署请用 systemd 托管 run.py。
- 启动前核对配置里的 instance.mode 和脚本一致，避免把个人服务的实例目录当团队服务跑（或者反过来）。
- 只停止本脚本启动的那个服务；不强制杀进程，不删除任何数据。
"""
import argparse
import fcntl
import hashlib
import http.client
import json
import os
import plistlib
import re
import signal
import socket
import subprocess
import sys
import time
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "venv" / "bin" / "python"


def _load_layers_module():
    """按文件路径加载配置合并规则：不导入 src.core.config 包，避免它在导入时按本进程环境加载配置。"""
    spec = importlib.util.spec_from_file_location("polaris_config_layers", ROOT / "src/core/config/layers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layers = _load_layers_module()


def _load_notify_targets_module():
    """通知目标的校验规则，与服务端共用（该文件不依赖项目其他模块）。"""
    spec = importlib.util.spec_from_file_location("polaris_notify_targets", ROOT / "src/domains/notify/targets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notify_targets = _load_notify_targets_module()

MODES = {
    "team": {"label": "团队服务", "port": 8710, "prefix": "local.polaris-team."},
    # 个人服务沿用原 start.sh 的 launchd 名称、日志位置，原来启动的服务也能用 stop-personal.sh 停掉
    "personal": {"label": "个人服务", "port": 8700, "prefix": "local.polaris."},
}
DB_KEYS = ("host", "port", "name", "user", "password", "connect_timeout", "read_timeout")
WILDCARD_HOSTS = ("", "0.0.0.0", "::")


def fail(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict:
    try:
        return layers.read_yaml(path)
    except ValueError as e:
        fail(str(e))


class Service:
    def __init__(self, mode: str, home: str | None = None, port: int | None = None, host: str | None = None):
        self.mode = mode
        self.name = MODES[mode]["label"]
        if mode == "team":
            home = home or os.environ.get("POLARIS_TEAM_HOME") or ROOT / "instances" / "team"
        else:
            home = home or ROOT
        self.home = Path(home).expanduser().resolve()
        self.local_config, self.legacy_config = layers.local_config_path(self.home)
        self.logs = self.home / "logs"
        self.log_file = self.logs / "polaris.log"
        self.state_file = self.logs / "polaris.service.json"
        self.label = MODES[mode]["prefix"] + hashlib.sha256(os.fsencode(str(self.home))).hexdigest()[:12]
        self._port_arg, self._host_arg = port, host
        # 提示里的命令：用了非默认实例目录时带上 --home，照着执行才能找到同一个服务
        default_home = (ROOT / "instances" / "team") if mode == "team" else ROOT
        suffix = f" --home {self.home}" if self.home != default_home.resolve() else ""
        self.stop_cmd = f"./stop-{mode}.sh{suffix}"
        self.use_state = False     # 停止/查看状态时按上次启动记下的端口找服务；启动时按配置
        self.config: dict = {}
        self.local: dict = {}      # 只有 config.local.yaml 本身的内容（核对模式用）
        self.config_warnings: list[str] = []

    # ------------------------------------------------------------------ 配置

    def load_config(self, required: bool = True) -> dict:
        """和服务端一样按三层合并；模式固定为脚本对应的模式（启动时也这样告诉服务进程）。"""
        for base in (ROOT / "config" / "config.yaml", ROOT / "config" / f"config.{self.mode}.yaml"):
            if not base.is_file():
                fail(f"缺少默认配置：{base}")
        if not self.local_config.is_file() and required:
            hint = ("\n第一次使用请先执行 ./start-team.sh --init 生成配置"
                    if self.mode == "team" else
                    f"\n可以从示例复制：cp {ROOT / 'config/config.local.yaml.example'} {self.local_config}")
            fail(f"缺少配置文件：{self.local_config}{hint}")
        self.local = load_yaml(self.local_config)
        try:
            self.config, _, self.config_warnings = layers.load_layers(ROOT, self.home, env_mode=self.mode)
        except ValueError as e:
            fail(str(e))
        # 模式不一致由 check() 给出更具体的说明，这里去掉重复的提示
        self.config_warnings = [w for w in self.config_warnings if not w.startswith("环境变量 POLARIS_MODE")]
        return self.config

    def section(self, name: str) -> dict:
        value = self.config.get(name)
        return value if isinstance(value, dict) else {}

    @property
    def port(self) -> int:
        if self._port_arg:
            return self._port_arg
        state = self.read_state() if self.use_state else {}
        if state.get("port"):
            return int(state["port"])
        try:
            return int(self.section("server").get("port") or MODES[self.mode]["port"])
        except (TypeError, ValueError):
            fail("server.port 必须是数字")

    @property
    def host(self) -> str:
        if self.mode == "personal":
            return "127.0.0.1"        # 个人服务里有私人数据，只给本机用
        if self._host_arg:
            return self._host_arg
        state = self.read_state() if self.use_state else {}
        if state.get("host"):
            return state["host"]
        return str(self.section("server").get("host") or "0.0.0.0")

    @property
    def probe_host(self) -> str:
        return "127.0.0.1" if self.host in WILDCARD_HOSTS else self.host

    def url(self) -> str:
        return f"http://{self.probe_host}:{self.port}"

    def check(self) -> tuple[list[str], list[str]]:
        """返回 (阻止启动的问题, 提醒)。"""
        cfg = self.load_config()
        problems, warnings = [], []
        llm = self.section("llm")
        missing = [f"llm.{k}" for k in ("api_key", "base_url", "model")
                   if not isinstance(llm.get(k), str) or not llm[k].strip()]
        if missing:
            problems.append("尚未填写：" + "、".join(missing))
        # 核对 config.local.yaml 本身写的模式：团队服务必须明确写 team；个人服务可以不写
        mode = layers.local_mode(self.local) or ("" if self.mode == "team" else "personal")
        if mode != self.mode:
            other = "start-team.sh" if mode == "team" else "start-personal.sh"
            if not mode:
                problems.append(f"{self.local_config} 里没有写 instance.mode。团队服务的配置必须明确写 instance.mode: team")
            else:
                problems.append(f"配置里的 instance.mode 是 {mode!r}，和{self.name}（{self.mode}）不一致。"
                                f"要启动这份配置请用 ./{other}；要当{self.name}用，请把 instance.mode 改成 {self.mode}")
        warnings.extend(self.config_warnings)
        if self.mode == "team":
            db = self.section("database")
            if not str(db.get("host") or "").strip():
                problems.append("没有配置 database.host：团队服务的公共数据存在 MySQL 里，没有数据库就无法读写")
            if self.section("server").get("admin_token"):
                warnings.append("配置了 server.admin_token：个人服务调接口时不带 token，会连不上团队服务（401）")
            if self.host not in WILDCARD_HOSTS and self.host.startswith("127."):
                warnings.append(f"只监听 {self.host}：其他机器连不上这个团队服务")
            if not self.section("embedding").get("api_key"):
                warnings.append("没有配置 embedding.api_key：公共笔记只能关键词搜索，公共知识库不能上传")
        else:
            if not str(self.section("remote").get("url") or "").strip():
                warnings.append("没有配置 remote.url：这是单机版，只有私人数据（要用公共数据，请填团队服务地址）")
        warnings.extend(self.check_webhooks())
        for file in (ROOT / "run.py", ROOT / "admin/dist/index.html", PYTHON):
            if not file.exists():
                problems.append(f"缺少运行文件：{file}")
        return problems, warnings

    def check_webhooks(self) -> list[str]:
        """notify.webhooks / notify.recipients 的校验，规则与服务端相同（src/domains/notify/targets.py）。"""
        notify = self.section("notify")
        targets, notes = notify_targets.load_targets(notify.get("webhooks"), notify.get("recipients"))
        notes = [f"{n}，该条将被跳过" if "第" in n else n for n in notes]
        channels = self.section("channels")
        for t in targets:
            if t.plugin and not (channels.get(t.plugin) or {}).get("enabled"):
                notes.append(f"通知目标 {t.name} 需要启用 {t.plugin} 渠道（channels.{t.plugin}.enabled），否则发送会失败")
            if self.mode == "personal" and "public" in t.scopes:
                notes.append(f"通知目标 {t.name} 会转发公共提醒：同一条公共提醒在 team 模式和每个 personal 模式都会触发，"
                             f"多人都这样配置时会收到重复通知（建议 personal 模式只转发 private）")
        if targets:
            print("✓ 通知目标：" + "、".join(f"{t.name}（{t.type}，提醒转发 {'/'.join(t.scopes)}）" for t in targets))
        if notify.get("api_token"):
            print("✓ 通知接口：已设置 notify.api_token")
        elif targets and self.mode == "team":
            notes.append("没有设置 notify.api_token：能访问团队服务端口的人都可以调用通知接口发消息")
        return notes

    def check_connections(self) -> list[str]:
        """连数据库 / 团队服务试一下。只是提醒：对方晚点起来也没关系，服务会在每次使用时重连。"""
        notes = []
        if self.mode == "team":
            db = self.section("database")
            try:
                import pymysql
                conn = pymysql.connect(host=str(db.get("host")), port=int(db.get("port") or 3306),
                                       user=str(db.get("user") or ""), password=str(db.get("password") or ""),
                                       database=str(db.get("name") or "") or None, connect_timeout=5,
                                       charset="utf8mb4")
                conn.close()
                notes.append(f"✓ 数据库可以连接：{db.get('user')}@{db.get('host')}:{db.get('port') or 3306}/{db.get('name')}")
            except Exception as e:
                notes.append(f"⚠ 数据库连接失败（服务仍会启动，使用公共数据时会报错）：{e}")
        else:
            url = str(self.section("remote").get("url") or "").strip().rstrip("/")
            if url:
                info = fetch_instance_url(url)
                if info is None:
                    notes.append(f"⚠ 团队服务现在连不上：{url}（个人服务仍会启动，先只显示私人数据）")
                elif info.get("mode") != "team":
                    notes.append(f"⚠ remote.url 指向的不是团队服务（对方模式：{info.get('mode')}），个人服务会拒绝连接它")
                else:
                    notes.append(f"✓ 团队服务可以连接：{info.get('name')}（{url}）")
        return notes

    # ------------------------------------------------------------------ 运行状态

    def instance_info(self, timeout: float = 1.0) -> dict | None:
        """服务在线时返回它的 /api/instance；旧版本没有这个接口时返回 {"mode": None}；连不上返回 None。"""
        token = str(self.section("server").get("admin_token") or "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        conn = http.client.HTTPConnection(self.probe_host, self.port, timeout=timeout)
        try:
            conn.request("GET", "/api/instance", headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            if resp.status == 200:
                try:
                    return json.loads(body)
                except ValueError:
                    pass    # 旧版本：被网页的兜底路由当成页面返回了
            conn.close()
            conn = http.client.HTTPConnection(self.probe_host, self.port, timeout=timeout)
            conn.request("GET", "/openapi.json")
            resp = conn.getresponse()
            if resp.status == 200 and b"Polaris Agent Server" in resp.read():
                return {"mode": None}
            return None
        except (OSError, http.client.HTTPException):
            return None
        finally:
            conn.close()

    def healthy(self) -> dict | None:
        info = self.instance_info()
        if info is not None and info.get("mode") not in (self.mode, None):
            fail(f"{self.url()} 上运行的是 {info.get('mode')} 模式的服务，不是{self.name}")
        return info

    def port_free(self) -> bool:
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        with socket.socket(family) as probe:
            try:
                probe.bind((self.host, self.port))
                return True
            except OSError:
                return False

    def read_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def write_state(self, **values) -> None:
        self.logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = {"mode": self.mode, "home": str(self.home), "host": self.host, "port": self.port, **values}
        self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self.state_file.chmod(0o600)

    def lock(self):
        self.logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = (self.logs / "polaris.control.lock").open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("另一个启动/停止操作正在进行，请等它结束。")
        return handle

    def command(self) -> list[str]:
        return [str(PYTHON), "-u", str(ROOT / "run.py"), "--home", str(self.home),
                "--host", self.host, "--port", str(self.port)]

    def environment(self) -> dict:
        return {"PATH": str(ROOT / "venv/bin") + ":/usr/bin:/bin:/usr/sbin:/sbin",
                "POLARIS_HOME": str(self.home), "POLARIS_MODE": self.mode, "PYTHONUNBUFFERED": "1",
                # 提醒时间按本地时间存：团队服务和所有个人服务要用同一个时区
                "TZ": os.environ.get("TZ", "Asia/Shanghai")}

    def describe(self, info: dict | None) -> str:
        if not info or not info.get("mode"):
            return ""
        return f"（{info.get('mode_label', self.name)} · {info.get('name', 'Polaris')}）"

    def print_started(self, pid, info) -> None:
        print(f"Polaris {self.name}启动成功{self.describe(info)}，PID：{pid}")
        if self.host in WILDCARD_HOSTS:
            print(f"访问：{self.url()}（其他机器用本机 IP 访问，端口 {self.port}）")
        else:
            print(f"访问：http://{self.host}:{self.port}")
        print(f"实例目录：{self.home}")
        print(f"日志：{self.log_file}")
        print(f"停止：{self.stop_cmd}")
        if self.mode == "team":
            print(f"个人服务连接时在 config.local.yaml 里写：remote.url: \"http://<本机IP>:{self.port}\"")


# ---------------------------------------------------------------------- 后台方式

def launchctl(*arguments):
    return subprocess.run(["/bin/launchctl", *arguments], capture_output=True, text=True)


def pid_of(state: str | None) -> str | None:
    match = re.search(r"^\s*pid = (\d+)", state or "", re.M)
    return match.group(1) if match else None


class Launchd:
    """macOS 用户级服务。描述文件只放在实例目录的 logs/ 下，不放进登录自启目录，也不含密钥。"""

    def __init__(self, svc: Service):
        self.svc = svc
        self.domain = f"gui/{os.getuid()}"
        self.target = f"{self.domain}/{svc.label}"
        if launchctl("print", self.domain).returncode:
            fail("无法访问当前 macOS 图形登录会话，请在本机登录后的终端运行。")

    def state(self) -> str | None:
        result = launchctl("print", self.target)
        if result.returncode == 113:
            return None
        if result.returncode:
            fail("无法查询服务状态：" + result.stderr.strip())
        return result.stdout

    def start(self) -> None:
        svc = self.svc
        existing = self.state()
        if existing is not None:
            if pid_of(existing) and svc.healthy():
                print(f"Polaris {svc.name}已在运行：{svc.url()}")
                return
            fail(f"{svc.name}已注册但尚未就绪。请查看 {svc.log_file}，先执行 {svc.stop_cmd} 再启动。")
        if not svc.port_free():
            fail(f"{svc.host}:{svc.port} 已被占用；不会停止或替换占用该端口的其他进程。")
        fd = os.open(svc.log_file, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(fd)
        plist_file = svc.logs / "polaris.launchd.plist"
        service = {
            "Label": svc.label,
            "ProgramArguments": svc.command(),
            "WorkingDirectory": str(ROOT),
            "EnvironmentVariables": svc.environment(),
            "StandardOutPath": str(svc.log_file),
            "StandardErrorPath": str(svc.log_file),
            "RunAtLoad": True,
            "KeepAlive": False,
            "ExitTimeOut": 30,
            "Umask": 0o077,
        }
        with plist_file.open("wb") as stream:
            plistlib.dump(service, stream)
        plist_file.chmod(0o600)
        result = launchctl("bootstrap", self.domain, str(plist_file))
        if result.returncode:
            fail("后台服务注册失败：" + result.stderr.strip() + "\n日志位置：" + str(svc.log_file))
        svc.write_state(backend="launchd")
        # 确认进程存活且 HTTP 就绪，不把"注册成功"当成"启动成功"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.state()
            pid = pid_of(state)
            if pid:
                info = svc.healthy()
                if info is not None:
                    svc.print_started(pid, info)
                    return
            if state is None or re.search(r"^\s*last exit code = -?\d", state, re.M):
                break
            time.sleep(0.5)
        fail(f"未确认服务就绪。请检查 {svc.log_file}\n如需重新启动，请先执行 {svc.stop_cmd}；脚本没有自动重试或清理文件。")

    def stop(self) -> None:
        svc = self.svc
        state = self.state()
        if state is None:
            print(f"{svc.name}未注册，无需停止。未停止其他进程，也未删除任何文件。")
            return
        if pid_of(state):
            result = launchctl("kill", "SIGTERM", self.target)
            if result.returncode and pid_of(self.state()):
                fail("无法请求进程正常退出：" + result.stderr.strip())
            deadline = time.monotonic() + 30
            while pid_of(self.state()):
                if time.monotonic() >= deadline:
                    fail(f"等待正常退出超过 30 秒；没有强制杀进程，也没有解除服务注册。\n"
                         f"请检查 {svc.log_file}，稍后再执行 {svc.stop_cmd}。")
                time.sleep(0.5)
        # 确认没有运行中的进程后才解除注册，不用 bootout 强制终止
        if self.state() is not None:
            result = launchctl("bootout", self.target)
            if result.returncode and self.state() is not None:
                fail("进程已退出，但解除服务注册失败：" + result.stderr.strip())
        if self.state() is not None:
            fail(f"尚未确认服务注册已解除，请稍后用 {svc.stop_cmd} --status 查看。")
        svc.state_file.unlink(missing_ok=True)
        print(f"Polaris {svc.name}已停止，服务注册已解除。")

    def status(self) -> None:
        svc = self.svc
        state = self.state()
        pid = pid_of(state)
        if state is None:
            print(f"{svc.name}未注册（没有检查用其他方式手动启动的进程）。")
        elif pid:
            info = svc.instance_info()
            health = f"HTTP 正常{svc.describe(info)}" if info is not None else "HTTP 暂无响应"
            print(f"{svc.name}正在运行，PID：{pid}，{health}")
            print(f"地址：{svc.url()}")
        else:
            print(f"{svc.name}已注册，但没有运行中的进程；可执行 {svc.stop_cmd} 解除注册。")
        print(f"实例目录：{svc.home}")


class Background:
    """非 macOS：后台进程 + 状态文件。不会开机自启，正式部署请用 systemd 托管 run.py。"""

    def __init__(self, svc: Service):
        self.svc = svc

    def running_pid(self) -> int | None:
        pid = self.svc.read_state().get("pid")
        if not pid:
            return None
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return None
        except PermissionError:
            pass
        # 确认这个 PID 还是我们启动的那个进程（PID 可能被系统复用）
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        return int(pid) if "run.py" in cmd and str(self.svc.home) in cmd else None

    def start(self) -> None:
        svc = self.svc
        pid = self.running_pid()
        if pid:
            if svc.healthy() is not None:
                print(f"Polaris {svc.name}已在运行：{svc.url()}")
                return
            fail(f"{svc.name}进程（PID {pid}）在运行但 HTTP 没有响应，请查看 {svc.log_file}，"
                 f"或先执行 {svc.stop_cmd}。")
        if not svc.port_free():
            fail(f"{svc.host}:{svc.port} 已被占用；不会停止或替换占用该端口的其他进程。")
        fd = os.open(svc.log_file, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        proc = subprocess.Popen(svc.command(), cwd=str(ROOT), env={**os.environ, **svc.environment()},
                                stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT,
                                start_new_session=True)
        os.close(fd)
        svc.write_state(backend="background", pid=proc.pid)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                fail(f"服务进程已退出（退出码 {proc.returncode}）。请检查 {svc.log_file}")
            info = svc.healthy()
            if info is not None:
                svc.print_started(proc.pid, info)
                print("注意：这种方式不会开机自启、崩溃后也不会自动拉起；正式部署请用 systemd 托管。")
                return
            time.sleep(0.5)
        fail(f"30 秒内未确认服务就绪（进程 {proc.pid} 仍在运行）。请检查 {svc.log_file}；"
             f"需要停止时执行 {svc.stop_cmd}。")

    def stop(self) -> None:
        svc = self.svc
        pid = self.running_pid()
        if not pid:
            if svc.state_file.exists():
                svc.state_file.unlink()      # 只是过期的状态记录
            print(f"{svc.name}没有在运行（没有检查用其他方式手动启动的进程）。")
            return
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        while self.running_pid():
            if time.monotonic() >= deadline:
                fail(f"等待正常退出超过 30 秒；没有强制杀进程。请检查 {svc.log_file}，稍后再执行 {svc.stop_cmd}。")
            time.sleep(0.5)
        svc.state_file.unlink(missing_ok=True)
        print(f"Polaris {svc.name}已停止（PID {pid}）。")

    def status(self) -> None:
        svc = self.svc
        pid = self.running_pid()
        if pid:
            info = svc.instance_info()
            health = f"HTTP 正常{svc.describe(info)}" if info is not None else "HTTP 暂无响应"
            print(f"{svc.name}正在运行，PID：{pid}，{health}")
            print(f"地址：{svc.url()}")
        else:
            print(f"{svc.name}没有在运行（没有检查用其他方式手动启动的进程）。")
        print(f"实例目录：{svc.home}")


def backend(svc: Service):
    choice = os.environ.get("POLARIS_SERVICE_BACKEND", "")
    if not choice and svc.use_state:
        choice = svc.read_state().get("backend", "")    # 停止/查看状态：沿用启动时的方式
    if choice == "background" or (choice != "launchd" and sys.platform != "darwin"):
        return Background(svc)
    return Launchd(svc)


def fetch_instance_url(url: str) -> dict | None:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.hostname, parts.port, timeout=5)
    try:
        conn.request("GET", (parts.path.rstrip("/") or "") + "/api/instance")
        resp = conn.getresponse()
        return json.loads(resp.read()) if resp.status == 200 else None
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------- 初始化团队服务配置

TEAM_TEMPLATE_HEADER = """\
# Polaris 团队服务（team）的本地配置。由 start-team.sh --init 生成；含密钥和数据库密码，权限 600，不要提交到 git。
# 默认值见项目的 config/config.yaml 和 config/config.team.yaml，这里只写与默认值不同的项。
# 端口和监听地址默认 0.0.0.0:8710，需要修改时在这里写 server.port / server.host。
# 配置说明见项目 README.md 的"配置文件"一节。
"""


def init_team(svc: Service) -> None:
    import yaml
    if svc.home == ROOT:
        fail("团队服务的实例目录不能是项目根目录（那是个人服务的实例目录），请用 --home 指定别的目录。")
    if svc.local_config.exists():
        fail(f"配置已存在，不会覆盖：{svc.local_config}")
    personal_cfg = layers.local_config_path(ROOT)[0]
    source = load_yaml(personal_cfg) if personal_cfg.is_file() else {}
    config: dict = {"instance": {"mode": "team", "name": "Polaris 团队服务"}}
    copied = []
    for key in ("llm", "embedding"):
        if isinstance(source.get(key), dict) and source[key]:
            config[key] = source[key]
            copied.append(key)
    db = source.get("database") if isinstance(source.get("database"), dict) else {}
    if db.get("host"):
        config["database"] = {k: db[k] for k in DB_KEYS if k in db}
        copied.append("database")
    else:
        config["database"] = {"host": "", "port": 3306, "name": "", "user": "", "password": ""}
    if "llm" not in config:
        config["llm"] = {"api_key": "", "base_url": "", "model": ""}
    (svc.home / "config").mkdir(mode=0o700, parents=True, exist_ok=True)
    text = TEAM_TEMPLATE_HEADER + "\n" + yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    fd = os.open(svc.local_config, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"已生成团队服务配置：{svc.local_config}（权限 600）")
    if copied:
        print(f"从个人服务的配置 {personal_cfg} 复制了：{'、'.join(copied)}（内容未显示）")
    todo = [k for k in ("llm", "database") if k not in copied]
    print("请检查并修改：instance.name（显示名）" + (f"，以及 {'、'.join(todo)}" if todo else ""))
    print("然后执行 ./start-team.sh --check 检查，./start-team.sh 启动。")


# ---------------------------------------------------------------------- 入口

def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)     # 和 stderr 的报错按实际顺序输出
    parser = argparse.ArgumentParser(prog="service.py", description="Polaris 服务启停")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("mode", choices=tuple(MODES))
    parser.add_argument("--home", help="实例目录（团队服务默认 instances/team，个人服务固定为项目根目录）")
    parser.add_argument("--port", type=int, help="端口（默认读 server.port；团队服务 8710，个人服务 8700）")
    parser.add_argument("--host", help="团队服务的监听地址（默认读 server.host，一般是 0.0.0.0）")
    parser.add_argument("--check", action="store_true", help="只检查配置和连接，不启动")
    parser.add_argument("--init", action="store_true", help="生成团队服务的配置模板")
    parser.add_argument("--status", action="store_true", help="只查看运行状态，不停止")
    args = parser.parse_args()

    prog = f"{args.action}-{args.mode}.sh"
    if args.action == "stop" and (args.check or args.init or args.port or args.host):
        fail(f"{prog} 只支持 --status 和 --home")
    if args.action == "start" and args.status:
        fail(f"查看状态请用 ./stop-{args.mode}.sh --status")
    if args.mode == "personal" and (args.home or args.host or args.init):
        fail("个人服务的实例目录固定是项目根目录、只监听 127.0.0.1，不支持 --home / --host / --init")
    if sys.platform != "darwin" and os.environ.get("POLARIS_SERVICE_BACKEND") == "launchd":
        fail("launchd 只在 macOS 上可用")

    svc = Service(args.mode, home=args.home, port=args.port, host=args.host)
    if args.init:
        init_team(svc)
        return
    if args.action == "stop":
        svc.use_state = True
        svc.load_config(required=False)
        _lock = None if args.status else svc.lock()
        runner = backend(svc)
        runner.status() if args.status else runner.stop()
        return

    problems, warnings = svc.check()
    if problems:
        fail("\n".join(f"✗ {p}" for p in problems) + f"\n配置文件：{svc.local_config}\n未启动服务。")
    for w in warnings:
        print(f"⚠ {w}")
    for note in svc.check_connections():
        print(note)
    if args.check:
        print(f"配置检查通过（{svc.name}）；未连接模型、未启动服务。")
        print(f"实例目录：{svc.home}")
        print(f"预定地址：{svc.host}:{svc.port}")
        return
    _lock = svc.lock()
    backend(svc).start()


if __name__ == "__main__":
    main()
