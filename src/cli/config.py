"""客户端连接配置。不导入服务端的 config 单例，也不读 config.local.yaml（模型密钥留在服务端）。

优先级：命令行参数 > 环境变量 > 配置文件 > 默认值。

- 配置文件默认是项目的 config/cli.yaml（已 gitignore），格式与服务端配置一致；可用 --config 或 POLARIS_CLI_CONFIG 指定；
- 运行状态（state.json、输入历史）默认在项目的 data/cli/；
- 设置 POLARIS_CLI_HOME 时，配置（cli.yaml）和状态都放在该目录。
"""
import ipaddress
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "http://127.0.0.1:8700"
DEFAULT_PROFILE = "local"

THEMES = ("auto", "light", "dark")
COLOR_MODES = ("auto", "always", "never")


class ConfigError(Exception):
    """本地配置错误（退出码 2）。"""


@dataclass
class ClientConfig:
    home: Path
    config_file: Path
    profile: str
    url: str
    token: str | None
    token_source: str               # "env" / "file:<path>" / "none"
    theme: str = "auto"
    color: str = "auto"
    persist_history: bool = False
    connect_timeout: float = 5.0
    read_timeout: float = 300.0     # 旧协议长工具调用没有心跳；超过这么久没任何数据就判为结果未知
    warnings: list[str] = field(default_factory=list)

    @property
    def state_file(self) -> Path:
        return self.home / "state.json"

    @property
    def history_file(self) -> Path:
        return self.home / "history"

    @property
    def state_key(self) -> str:
        # v1 只能用"profile + 规范化 URL"区分本地状态，识别不出同一 URL 后面换了实例
        return f"{self.profile}|{self.url}"


def cli_home() -> Path:
    """运行状态目录。"""
    env = os.environ.get("POLARIS_CLI_HOME")
    return Path(env).expanduser() if env else PROJECT_ROOT / "data" / "cli"


def default_config_file() -> Path:
    env = os.environ.get("POLARIS_CLI_HOME")
    if env:
        return Path(env).expanduser() / "cli.yaml"
    return PROJECT_ROOT / "config" / "cli.yaml"


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"无效的服务地址：{url!r}（需要 http:// 或 https:// 开头）")
    netloc = parts.hostname.lower()
    if ":" in netloc:
        netloc = f"[{netloc}]"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def is_loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _read_config_file(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml          # 惰性导入：--help 等路径不加载
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"配置文件无法解析：{path}（{e}）")
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件的顶层必须是 YAML 对象：{path}")
    return data


def _loose_permission(path: Path) -> bool:
    try:
        return bool(path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
    except OSError:
        return False


def _read_token_file(path: Path, warnings: list[str]) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise ConfigError(f"无法读取 token 文件：{path}（{e}）")
    if _loose_permission(path):
        warnings.append(f"token 文件 {path} 对其他用户可读，建议 chmod 600")
    if not token:
        raise ConfigError(f"token 文件为空：{path}")
    return token


def load_config(*, config_path: str | None = None, profile: str | None = None, url: str | None = None,
                token_file: str | None = None, theme: str | None = None,
                color: str | None = None) -> ClientConfig:
    home = cli_home()
    warnings: list[str] = []
    explicit = config_path or os.environ.get("POLARIS_CLI_CONFIG")
    cfg_file = Path(explicit).expanduser() if explicit else default_config_file()
    data = _read_config_file(cfg_file)

    profile_name = profile or os.environ.get("POLARIS_PROFILE") or data.get("default_profile") or DEFAULT_PROFILE
    profiles = data.get("profiles", {})
    prof = profiles.get(profile_name)
    if prof is None:
        if profile and profiles:
            raise ConfigError(f"配置里没有 profile「{profile_name}」，已有：{', '.join(profiles)}")
        prof = {}

    raw_url = url or os.environ.get("POLARIS_URL") or prof.get("url") or DEFAULT_URL
    norm_url = normalize_url(raw_url)

    # 凭据只来自环境变量或受限文件；不提供命令行明文参数，避免进 shell history / 进程列表
    if os.environ.get("POLARIS_ADMIN_TOKEN"):
        token, source = os.environ["POLARIS_ADMIN_TOKEN"].strip(), "env"
    elif token_file or prof.get("token_file"):
        p = Path(token_file or prof["token_file"]).expanduser()
        token, source = _read_token_file(p, warnings), f"file:{p}"
    else:
        token, source = None, "none"

    if not is_loopback(norm_url):
        if urlsplit(norm_url).scheme != "https":
            raise ConfigError(f"远程地址必须使用 https：{norm_url}（本机地址才允许 http）")
        if not token:
            warnings.append("连接的是远程地址但没有配置访问凭据（POLARIS_ADMIN_TOKEN 或 token_file）")

    ui = data.get("ui", {})
    net = data.get("network", {})
    theme_v = theme or ui.get("theme", "auto")
    color_v = color or ui.get("color", "auto")
    if theme_v not in THEMES:
        raise ConfigError(f"theme 只能是 {'/'.join(THEMES)}：{theme_v!r}")
    if color_v not in COLOR_MODES:
        raise ConfigError(f"color 只能是 {'/'.join(COLOR_MODES)}：{color_v!r}")
    if cfg_file.exists() and _loose_permission(cfg_file):
        warnings.append(f"配置文件 {cfg_file} 对其他用户可读，建议 chmod 600")

    try:
        connect_timeout = float(net.get("connect_timeout", 5))
        read_timeout = float(net.get("read_timeout", 300))
    except (TypeError, ValueError):
        raise ConfigError("network.connect_timeout / read_timeout 必须是数字")

    return ClientConfig(
        home=home, config_file=cfg_file, profile=profile_name, url=norm_url,
        token=token or None, token_source=source, theme=theme_v, color=color_v,
        persist_history=bool(ui.get("persist_history", False)),
        connect_timeout=connect_timeout, read_timeout=read_timeout, warnings=warnings,
    )
