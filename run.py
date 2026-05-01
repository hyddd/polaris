#!/usr/bin/env python3
"""Polaris 统一启动入口。

用法:
    source venv/bin/activate && python run.py          # 生产模式
    source venv/bin/activate && python run.py --dev    # 开发模式（热重载）

启动 Agent Server（主进程）。Channel 插件由 Server 自动发现并启动。
"""

import sys
import uvicorn


def main():
    dev = "--dev" in sys.argv

    print("=" * 50)
    print("  Polaris Agent Server")
    print("  http://localhost:8700")
    print("  /chat  /chat/stream  /sessions")
    print("=" * 50)
    print()
    if dev:
        print("  模式: 开发（文件变更自动重启）")
    else:
        print("  模式: 生产")
    print("  Channel 插件将在 Server 启动时自动加载...")
    print()

    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=8700,
        loop="asyncio",
        reload=dev,
    )


if __name__ == "__main__":
    main()
