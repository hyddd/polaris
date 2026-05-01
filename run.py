#!/usr/bin/env python3
"""Polaris 统一启动入口。

用法:
    source venv/bin/activate && python run.py

启动 Agent Server（主进程）。Channel 插件由 Server 自动发现并启动。
"""

import uvicorn


def main():
    print("=" * 50)
    print("  Polaris Agent Server")
    print("  http://localhost:8700")
    print("  /chat  /chat/stream  /sessions")
    print("=" * 50)
    print()
    print("Channel 插件将在 Server 启动时自动加载...")
    print()

    uvicorn.run("src.server:app", host="0.0.0.0", port=8700, loop="asyncio")


if __name__ == "__main__":
    main()
