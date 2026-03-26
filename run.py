#!/usr/bin/env python3
"""Polaris 统一启动入口 — 同时启动 Chainlit Web + 飞书 Bot。

用法:
    source venv/bin/activate && python run.py

飞书 Bot 为可选：只有配置了 FEISHU_APP_ID 和 FEISHU_APP_SECRET 才会启动。
启动后 Web 端访问 http://localhost:8000，飞书端在飞书 App 内 @机器人 对话。
"""

import os
import sys
import subprocess
import threading
from dotenv import load_dotenv

load_dotenv()


def start_feishu_bot():
    """在后台线程启动飞书 Bot WebSocket 连接。"""
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("[feishu] 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，跳过飞书 Bot")
        return

    print(f"[feishu] 启动飞书 Bot (App ID: {app_id[:8]}...)")

    def _run():
        from src.feishu_bot import PolarisFeishuBot
        try:
            bot = PolarisFeishuBot()
            bot.start()
        except Exception as e:
            print(f"[feishu] Bot 启动失败: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print("[feishu] 飞书 Bot 已启动（后台 WebSocket 长连接）")


def main():
    print("=" * 50)
    print("  Polaris — 个人效率 AI Agent")
    print("  Web: http://localhost:8000")
    print("  飞书: 配置 FEISHU_APP_ID 后自动启用")
    print("=" * 50)
    print()

    start_feishu_bot()

    # 启动 Chainlit（主进程，处理 Ctrl+C）
    venv_python = sys.executable
    chainlit_bin = os.path.join(os.path.dirname(venv_python), "chainlit")
    if not os.path.exists(chainlit_bin):
        chainlit_bin = "chainlit"

    print("[web] 启动 Chainlit Web UI ...")
    print()

    subprocess.run([chainlit_bin, "run", "src/chainlit_app.py", "--port", "8000"])


if __name__ == "__main__":
    main()
