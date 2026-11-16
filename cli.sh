#!/bin/bash
# 进入 Polaris 终端客户端；只连接已运行的服务，不启动或停止服务、不安装依赖、不读模型密钥。
# 用法：./cli.sh [polaris 参数]，例如 ./cli.sh --resume、./cli.sh -p "今天有什么安排"、./cli.sh doctor
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="$ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  printf '缺少项目虚拟环境：%s\n' "$PYTHON" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import prompt_toolkit' 2>/dev/null; then
  printf '虚拟环境缺少 prompt_toolkit，请先安装：uv pip install --python %s "prompt_toolkit>=3.0.53,<4"\n' "$PYTHON" >&2
  exit 1
fi
# 不 cd 到项目目录：--token-file、--config 等相对路径仍按调用时的当前目录解析
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m src.cli "$@"
