#!/usr/bin/env bash
# deploy.sh — 部署 Polaris 到远程 Ubuntu 主机
#
# 用法:
#   ./deploy.sh              # 仅同步文件
#   ./deploy.sh --setup      # 同步 + 安装依赖 + 构建前端 + 配置 systemd
#   ./deploy.sh --run        # 同步 + 启动/重启服务
#   ./deploy.sh --setup --run # 全流程

set -euo pipefail

REMOTE="root@yankang.space"
REMOTE_DIR="~/Code/polaris"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="polaris"

DO_SETUP=false
DO_RUN=false

for arg in "$@"; do
    case "$arg" in
        --setup) DO_SETUP=true ;;
        --run)   DO_RUN=true ;;
        *)       echo "未知参数: $arg"; exit 1 ;;
    esac
done

echo "=== Polaris 部署 ==="
echo "本地: $LOCAL_DIR"
echo "远程: $REMOTE:$REMOTE_DIR"
echo ""

# 1. 同步文件
echo "[1/3] 同步文件..."
rsync -avz --progress \
    --exclude='.env' \
    --exclude='.git/' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='data/' \
    --exclude='.DS_Store' \
    "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/"
echo ""

# 2. 远程安装依赖 + 构建前端 + 配置 systemd
if $DO_SETUP; then
    echo "[2/3] 远程安装依赖..."
    ssh "$REMOTE" bash <<'SETUP_EOF'
        set -euo pipefail
        cd ~/Code/polaris

        # 创建虚拟环境并安装依赖
        echo "安装 Python 依赖..."
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip -q
        if [ -f requirements.txt ]; then
            pip install -r requirements.txt -q
        fi

        # 安装 Node.js 依赖并构建前端
        echo "构建前端..."
        if [ -d admin ] && [ -f admin/package.json ]; then
            cd admin
            if ! command -v node &> /dev/null; then
                echo "安装 Node.js..."
                curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
                apt-get install -y nodejs
            fi
            npm install --production=false -q
            npm run build
            cd ..
            echo "前端构建完成"
        fi

        # 创建日志目录
        mkdir -p logs

        # 创建 systemd service 文件
        echo "配置 systemd 服务..."
        cat > /etc/systemd/system/polaris.service <<EOF
[Unit]
Description=Polaris Agent Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python run.py
Restart=on-failure
RestartSec=5
Environment=PATH=$(pwd)/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable polaris
        echo "systemd 服务已配置并启用"
SETUP_EOF
    echo ""
fi

# 3. 启动/重启服务
if $DO_RUN; then
    echo "[3/3] 启动服务..."
    ssh "$REMOTE" bash <<'RUN_EOF'
        systemctl daemon-reload
        systemctl restart polaris
        sleep 2
        systemctl status polaris --no-pager -l
RUN_EOF
    echo ""
    echo "常用命令:"
    echo "  ssh $REMOTE systemctl status polaris    # 查看状态"
    echo "  ssh $REMOTE journalctl -u polaris -f     # 查看日志"
    echo "  ssh $REMOTE systemctl restart polaris    # 重启"
fi

echo "=== 部署完成 ==="
