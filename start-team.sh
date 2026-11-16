#!/bin/bash
# 启动团队服务（team）：只保存公共数据，默认监听 0.0.0.0:8710，实例目录 instances/team/。
# 第一次使用：./start-team.sh --init 生成配置，改好后 ./start-team.sh --check 检查，再 ./start-team.sh 启动。
# 用法：./start-team.sh [--init] [--check] [--home 目录] [--port 端口] [--host 地址]
# macOS 用 launchd 托管；其他系统用后台进程（不会开机自启，正式部署请用 systemd 托管 run.py）。
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="$ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  printf '缺少项目虚拟环境：%s\n' "$PYTHON" >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/service.py" start team "$@"
