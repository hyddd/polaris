#!/bin/bash
# 启动个人服务（personal）：私人数据 + 通过 remote.url 访问团队服务的公共数据。
# 只监听 127.0.0.1:8700，实例目录是项目根目录（config/、data/、logs/）。
# 用法：./start-personal.sh [--check] [--port 端口]
# macOS 用 launchd 托管；其他系统用后台进程（不会开机自启，正式部署请用 systemd 托管 run.py）。
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="$ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  printf '缺少项目虚拟环境：%s\n' "$PYTHON" >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/service.py" start personal "$@"
