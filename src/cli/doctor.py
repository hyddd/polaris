"""只读诊断：polaris status / polaris doctor。

不发送任何聊天 POST、不调用模型、不修改配置、不安装或删除任何东西。
网络调用只有 GET：/openapi.json（接口与版本）、/api/instance（服务模式）和 /api/status（认证与服务概览）。
"""
import importlib.metadata as md
import os
import stat
import sys

from src.cli.application.controller import Controller
from src.cli.client import ClientError
from src.cli.config import ClientConfig, is_loopback
from src.cli.ui.render import Renderer, color_enabled

OK, WARN, FAIL = "ok", "warn", "fail"
MARK = {OK: "✓", WARN: "⚠", FAIL: "✗"}


async def collect(ctrl: Controller, cfg: ClientConfig, full: bool) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    if full:
        py = sys.version_info
        checks.append((OK if py >= (3, 12) else FAIL, "Python", f"{py.major}.{py.minor}.{py.micro}"))
        for pkg in ("httpx", "rich", "prompt_toolkit"):
            try:
                checks.append((OK, pkg, md.version(pkg)))
            except md.PackageNotFoundError:
                level = WARN if pkg == "prompt_toolkit" else FAIL
                checks.append((level, pkg, "未安装（交互模式需要）" if pkg == "prompt_toolkit" else "未安装"))
        tty = sys.stdin.isatty() and sys.stdout.isatty()
        checks.append((OK, "终端", f"{'TTY' if tty else '非 TTY'} · 颜色{'开启' if color_enabled(cfg.color, sys.stdout) else '关闭'}"
                       f" · TERM={os.environ.get('TERM', '-')}{' · NO_COLOR' if os.environ.get('NO_COLOR') else ''}"))
        if cfg.config_file.exists():
            loose = cfg.config_file.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)
            checks.append((WARN if loose else OK, "配置文件", f"{cfg.config_file}{'（权限过宽，建议 600）' if loose else ''}"))
        else:
            checks.append((OK, "配置文件", f"{cfg.config_file}（不存在，使用默认值）"))
        checks.append((OK, "本地状态目录", str(cfg.home)))
        for w in cfg.warnings:
            checks.append((WARN, "配置", w))

    checks.append((OK, "服务地址", f"{cfg.url}（profile：{cfg.profile}{'，本机' if is_loopback(cfg.url) else '，远程'}）"))
    checks.append((OK, "访问凭据", {"none": "未配置（服务端未开启鉴权时不需要）", "env": "环境变量 POLARIS_ADMIN_TOKEN"}
                   .get(cfg.token_source, cfg.token_source.replace("file:", "文件 "))))

    info = await ctrl.probe()
    if not info.reachable:
        checks.append((FAIL, "连接", f"连不上：{info.error}；服务没运行的话在项目目录执行 ./start-personal.sh（团队服务用 ./start-team.sh）"))
        return checks
    checks.append((OK, "连接", "GET /openapi.json 正常"))
    if info.missing:
        checks.append((FAIL, "接口", "缺少：" + "、".join(info.missing)))
    else:
        checks.append((OK, "接口", "终端客户端依赖的接口齐全"))
    if info.fixed_backend:
        checks.append((OK, "服务端版本", "已包含 2026-11-09 修复"))
    else:
        checks.append((FAIL, "服务端版本", "修复前的旧代码：流式对话会覆盖会话历史，请重启服务（./stop-personal.sh && ./start-personal.sh，团队服务用 -team）"))

    try:
        from src.cli.application.controller import describe_instance
        inst = await ctrl.instance()
        checks.append((OK if inst else WARN, "服务模式", describe_instance(inst)))
    except ClientError as e:
        checks.append((WARN, "服务模式", str(e)))

    try:
        st = await ctrl.server_status()
        checks.append((OK, "认证", "GET /api/status 通过"))
        chans = "、".join(f"{c['name']}{'' if c.get('configured') else '(未配置)'}" for c in st.get("channels", []))
        checks.append((OK, "服务概览", f"工具 {len(st.get('tools', []))} 个 · 调度任务 {len(st.get('jobs', []))} 个 · 渠道：{chans or '无'}"))
        team = st.get("team")
        if team:
            checks.append((OK, "团队服务", f"已连接：{team['name']}") if team.get("ok")
                          else (WARN, "团队服务", f"连不上，暂时只有私人数据：{team.get('error')}"))
    except ClientError as e:
        checks.append((FAIL if e.kind == "auth" else WARN, "认证" if e.kind == "auth" else "服务概览", str(e)))

    checks.append((WARN, "模型连通性", "未测试（诊断不调用模型，避免产生费用）"))
    return checks


def render(r: Renderer, checks: list[tuple[str, str, str]]) -> int:
    for level, name, detail in checks:
        style = {OK: "ok", WARN: "warn", FAIL: "err"}[level]
        r.line(f"{MARK[level]} {name}：{detail}", style)
    if any(level == FAIL and name in ("连接", "认证") for level, name, _ in checks):
        return 3
    if any(level == FAIL for level, _, _ in checks):
        return 4
    return 0


def to_json(checks) -> list[dict]:
    return [{"level": level, "check": name, "detail": detail} for level, name, detail in checks]
