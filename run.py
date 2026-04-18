#!/usr/bin/env python3
"""Polaris 统一启动入口。

用法:
    source venv/bin/activate && python run.py

启动 Agent Server（主进程），可选并行启动飞书 Bot。
Chainlit 需单独启动：chainlit run src/chainlit_app.py
"""

import os
import sys
import threading
from dotenv import load_dotenv

load_dotenv()


def start_feishu_bot():
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("[feishu] 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，跳过")
        return

    def _run():
        from src.feishu_bot import PolarisFeishuBot
        try:
            bot = PolarisFeishuBot()
            bot.start()
        except Exception as e:
            print(f"[feishu] 启动失败: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print("[feishu] 已后台启动")


def main():
    print("=" * 50)
    print("  Polaris Agent Server")
    print("  http://localhost:8700")
    print("  /chat  /chat/stream  /sessions")
    print("=" * 50)
    print()

    start_feishu_bot()

    import uvicorn
    uvicorn.run("src.server:app", host="0.0.0.0", port=8700)


if __name__ == "__main__":
    main()
