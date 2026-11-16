"""polaris 命令入口：参数解析与模式分发。

这个文件顶层只导入标准库：--help、参数错误这些路径不加载 httpx / rich / prompt_toolkit，
更不会碰服务端的 src.agent、src.server、src.core（不读模型密钥、不起线程、不写文件）。
"""
import argparse
import asyncio
import os
import sys

OUTPUTS = ("text", "json", "ndjson")

EPILOG = """\
示例：
  polaris                                   开始新会话（和 claude 一样）
  polaris -c                                继续最近的会话
  polaris --resume                          打开会话选择器
  polaris --resume 周报                      按名称或 ID 直接恢复会话
  polaris -n 周报                            开始新会话并命名
  polaris -p "今天有哪些未完成事项？"         单次提问（默认新建独立会话）
  polaris -c -p "接着刚才的说"               在最近的会话里单次提问
  polaris -p "整理这些事项" --output json    输出单个 JSON 结果
  echo "帮我列一下待办" | polaris --stdin -r <ID>
  polaris todo list --status pending        结构化查询（不经过模型）
  polaris doctor                            只读诊断（不调用模型）

退出码：0 成功 · 2 参数/配置错误 · 3 连接/认证失败 · 4 服务端失败/不存在/冲突
        6 聊天结果未确认（旧聊天协议不提供提交确认）· 130 用户中断
凭据：POLARIS_ADMIN_TOKEN 环境变量或 --token-file（不支持命令行明文 token）。
"""


def _common(parser: argparse.ArgumentParser, suppress: bool) -> None:
    """全局参数：主命令和各子命令都能用（子命令里用 SUPPRESS，避免覆盖主命令上已给的值）。"""
    d = argparse.SUPPRESS if suppress else None
    g = parser.add_argument_group("连接与显示")
    g.add_argument("--url", default=d, help="服务地址（默认 http://127.0.0.1:8700）")
    g.add_argument("--profile", default=d, help="使用配置文件里的 profile")
    g.add_argument("--config", default=d, help="配置文件路径（默认 config/cli.yaml）")
    g.add_argument("--token-file", default=d, help="从文件读取访问凭据（建议权限 600）")
    g.add_argument("--theme", choices=("auto", "light", "dark"), default=d, help="配色")
    g.add_argument("--color", choices=("auto", "always", "never"), default=d, help="是否输出颜色")
    g.add_argument("--output", choices=OUTPUTS, default=d, help="非交互输出格式（默认 text）")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="polaris", description="Polaris 终端客户端：连接已运行的 Polaris 服务对话与查询。",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(p, suppress=False)
    chat_opts = p.add_argument_group("对话")
    chat_opts.add_argument("-p", "--print", dest="prompt", metavar="消息", help="单次提问后退出")
    chat_opts.add_argument("--stdin", action="store_true", help="从标准输入读取一条消息，单次提问后退出")
    # 会话参数与 Claude Code 一致：-c 继续最近的会话；-r 不带值打开选择器，带名称或 ID 直接恢复；-n 给新会话命名
    chat_opts.add_argument("-c", "--continue", dest="cont", action="store_true", help="继续最近的会话")
    chat_opts.add_argument("-r", "--resume", nargs="?", const="", default=None, metavar="名称或ID",
                           help="恢复会话：不带值打开会话选择器，带名称或 ID 直接恢复")
    chat_opts.add_argument("-n", "--name", dest="new_name", metavar="名称", help="开始新会话并命名")
    chat_opts.add_argument("--session", metavar="ID", help=argparse.SUPPRESS)   # 旧参数，等同 --resume <ID>

    sub = p.add_subparsers(dest="command", metavar="命令")

    def add(name, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        _common(sp, suppress=True)
        return sp

    add("chat", "进入交互对话（与不带命令相同）")
    add("status", "连接状态、服务端版本与当前会话（不调用模型）")
    add("doctor", "只读诊断：客户端环境、连接、认证、接口能力（不调用模型、不修改任何东西）")

    s = add("session", "会话管理")
    s_sub = s.add_subparsers(dest="action", metavar="操作", required=True)
    for name, help_ in (("list", "列出全部会话"), ("create", "新建会话"), ("show", "查看会话详情和最近消息")):
        sp = s_sub.add_parser(name, help=help_)
        _common(sp, suppress=True)
        if name == "create":
            sp.add_argument("--name", help="会话名称")
        if name == "show":
            sp.add_argument("session_id", metavar="ID")
            sp.add_argument("--limit", type=int, default=20, help="显示最近多少条消息")

    t = add("todo", "待办（只读）")
    t_list = t.add_subparsers(dest="action", metavar="操作", required=True).add_parser("list", help="列出待办")
    _common(t_list, suppress=True)
    t_list.add_argument("--status", choices=("pending", "in_progress", "done", "all"), default="all")

    c = add("calendar", "日程（只读）")
    c_list = c.add_subparsers(dest="action", metavar="操作", required=True).add_parser("list", help="列出日程")
    _common(c_list, suppress=True)
    c_list.add_argument("--date", metavar="YYYY-MM-DD", help="只看某一天")

    r = add("reminder", "提醒（只读）")
    r_list = r.add_subparsers(dest="action", metavar="操作", required=True).add_parser("list", help="列出提醒")
    _common(r_list, suppress=True)
    r_list.add_argument("--status", choices=("active", "paused", "cancelled", "failed", "all"), default="all")
    return p


def _usage_error(parser: argparse.ArgumentParser, msg: str) -> int:
    parser.print_usage(sys.stderr)
    print(f"polaris: 错误：{msg}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:          # --help 或参数错误
        return int(e.code or 0)

    command = ns.command or "chat"
    output = ns.output or "text"
    one_shot = ns.prompt is not None or ns.stdin

    if ns.session:
        if ns.resume is not None:
            return _usage_error(parser, "--resume 与 --session 不能同时使用")
        ns.resume = ns.session
    picks = [x for x in (ns.cont, ns.resume is not None, bool(ns.new_name)) if x]
    if ns.prompt is not None and ns.stdin:
        return _usage_error(parser, "-p 与 --stdin 不能同时使用")
    if command != "chat" and (one_shot or picks):
        return _usage_error(parser, f"-p / --stdin / -c / -r / -n 不能和 {command} 命令一起用")
    if len(picks) > 1:
        return _usage_error(parser, "-c、--resume、-n 只能用一个")
    if one_shot and ns.resume == "":
        return _usage_error(parser, "单次提问不能打开会话选择器；请用 --resume <名称或ID> 或 -c")
    if command == "chat" and not one_shot:
        if output != "text":
            return _usage_error(parser, "--output json/ndjson 只用于 -p、--stdin 和查询命令")
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            # 没有终端又没给输入：不强行进交互界面，也不隐式去读 stdin
            return _usage_error(parser, "当前不是交互终端；请用 -p \"消息\" 或 --stdin 指定输入")

    message = None
    if one_shot:
        message = sys.stdin.read() if ns.stdin else ns.prompt
        if not message.strip():
            return _usage_error(parser, "消息为空")

    from src.cli.config import ConfigError, load_config
    try:
        cfg = load_config(config_path=ns.config, profile=ns.profile, url=ns.url, token_file=ns.token_file,
                          theme=ns.theme, color=ns.color)
    except ConfigError as e:
        print(f"polaris: 配置错误：{e}", file=sys.stderr)
        return 2
    for w in cfg.warnings:
        print(f"polaris: 警告：{w}", file=sys.stderr)

    try:
        return asyncio.run(_dispatch(ns, cfg, command, output, message))
    except KeyboardInterrupt:
        return 130


async def _dispatch(ns, cfg, command: str, output: str, message: str | None) -> int:
    from src.cli.application.controller import Controller, SessionNotFound
    from src.cli.client import ClientError, PolarisClient
    from src.cli.storage import StateStore
    from src.cli.ui.render import Renderer

    store = StateStore(cfg.state_file, cfg.state_key)
    if store.warning:
        print(f"polaris: 警告：{store.warning}", file=sys.stderr)

    async with PolarisClient(cfg) as client:
        ctrl = Controller(client)

        if command == "chat" and message is None:
            from src.cli.ui.repl import Repl
            mode = "continue" if ns.cont else "resume" if ns.resume is not None else "new"
            repl = Repl(ctrl, cfg, store, Renderer(color=cfg.color, theme=cfg.theme))
            return await repl.run(mode, target=ns.resume or None, name=ns.new_name)

        if command == "chat":
            from src.cli.ui.plain import run_once
            err = Renderer(sys.stderr, color=cfg.color)
            try:
                session_id = await _one_shot_session(ctrl, store, ns)
            except ClientError as e:
                err.error(str(e))
                return e.exit_code
            except SessionNotFound as e:
                err.error(f"会话不存在：{e}")
                return 4
            except LookupError as e:
                err.error(str(e))
                return 4
            return await run_once(ctrl, message, session_id, output, color=cfg.color, new_name=ns.new_name)

        err = Renderer(sys.stderr, color=cfg.color, theme=cfg.theme)
        try:
            return await _structured(ns, cfg, command, output, ctrl, store)
        except SessionNotFound as e:
            err.error(f"会话不存在：{e}")
            return 4
        except ClientError as e:
            err.error(str(e))
            return e.exit_code


async def _one_shot_session(ctrl, store, ns) -> str | None:
    """-p / --stdin 用哪个会话：-c 最近的；-r 指定的（必须唯一）；都没给返回 None（新建独立会话）。"""
    if not ns.cont and not ns.resume:
        return None
    sessions, _ = await ctrl.list_sessions()
    if ns.cont:
        last = store.last_session
        if last and any(s["session_id"] == last for s in sessions):
            return last
        if not sessions:
            raise LookupError("没有可以继续的会话")
        return sessions[0]["session_id"]
    target = ns.resume
    hits = [s for s in sessions if s["session_id"] == target or s["name"] == target] or \
        [s for s in sessions if s["session_id"].startswith(target)]
    if len(hits) == 1:
        return hits[0]["session_id"]
    if not hits:
        return target            # 交给 run_once 报"会话不存在"，--output json 时仍输出失败对象
    raise LookupError(f"「{target}」对应多个会话，请用完整的会话 ID")


async def _structured(ns, cfg, command, output, ctrl, store) -> int:
    from src.cli import doctor
    from src.cli.ui import views
    from src.cli.ui.plain import print_json
    from src.cli.ui.render import Renderer

    r = Renderer(color=cfg.color, theme=cfg.theme)
    as_json = output in ("json", "ndjson")

    if command in ("status", "doctor"):
        checks = await doctor.collect(ctrl, cfg, full=(command == "doctor"))
        if command == "status" and store.last_session:
            checks.append(("ok", "上次会话", store.last_session))
        if as_json:
            print_json(doctor.to_json(checks))
            return 3 if any(c[0] == "fail" and c[1] in ("连接", "认证") for c in checks) else \
                (4 if any(c[0] == "fail" for c in checks) else 0)
        return doctor.render(r, checks)

    if command == "session":
        if ns.action == "list":
            sessions, _ = await ctrl.list_sessions()
            if as_json:
                print_json(sessions)
            else:
                views.show_sessions(r, sessions, current=store.last_session)
        elif ns.action == "create":
            created = await ctrl.create_session(ns.name)
            if as_json:
                print_json(created)
            else:
                r.ok(f"已新建会话「{created['name']}」：{created['session_id']}")
        elif ns.action == "show":
            detail = await ctrl.session_detail(ns.session_id)
            if as_json:
                print_json(detail)
            else:
                stats = detail.get("token_stats", {})
                r.line(f"{detail.get('name')}（{detail.get('session_id')}）· 消息 {stats.get('message_count', '?')} 条", "accent")
                views.show_history(r, detail.get("messages", []), ns.limit)
        return 0

    fetch, show = {
        "todo": (lambda: ctrl.todos(ns.status), views.show_todos),
        "calendar": (lambda: ctrl.calendar(ns.date), views.show_calendar),
        "reminder": (lambda: ctrl.reminders(ns.status), views.show_reminders),
    }[command]
    items = await fetch()
    if as_json:
        print_json(items)
    else:
        show(r, items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
