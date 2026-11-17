#!/bin/bash
# 停止 start-team.sh 启动的团队服务；保留配置、数据和日志。
# 用法：./stop-team.sh [--status]
# macOS 用 launchd 托管；其他系统用后台进程（不会开机自启，正式部署请用 systemd 托管 run.py）。
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="$ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  printf '缺少项目虚拟环境：%s\n' "$PYTHON" >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/service.py" stop team "$@"
