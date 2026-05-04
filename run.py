#!/usr/bin/env python3
"""Polaris 统一启动入口。

用法:
    source venv/bin/activate
    python run.py                              # 默认实例 (port 8700)
    python run.py --dev                        # 开发模式（热重载）
    python run.py --home /opt/polaris-demo --port 8800  # 多实例

多实例部署:
    POLARIS_HOME 指向独立数据目录（config.local.yaml + data/），
    不同实例互不影响。
"""

import os
import sys
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Polaris Agent Server")
    parser.add_argument("--dev", action="store_true", help="开发模式（热重载）")
    parser.add_argument("--port", type=int, default=8700, help="监听端口（默认 8700）")
    parser.add_argument("--home", type=str, default=None,
                        help="数据目录路径。多实例时指向独立目录。默认项目根 data/")
    parser.add_argument("--demo", type=int, default=0, metavar="N",
                        help="试用模式，限制每IP每日消息数（默认 0 不启用）")
    args = parser.parse_args()

    if args.home:
        os.environ["POLARIS_HOME"] = args.home
    if args.demo:
        os.environ["DEMO_DAILY_MESSAGES"] = str(args.demo)

    print("=" * 50)
    print("  Polaris Agent Server")
    print(f"  http://localhost:{args.port}")
    if args.home:
        print(f"  DATA: {args.home}/data/")
    if args.demo:
        print(f"  试用模式: 每 IP 每日 {args.demo} 条消息")
    print("=" * 50)
    print()
    if args.dev:
        print("  模式: 开发（文件变更自动重启）")
    else:
        print("  模式: 生产")
    print(f"  端口: {args.port}")
    print()

    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=args.port,
        loop="asyncio",
        reload=args.dev,
    )


if __name__ == "__main__":
    main()
