#!/usr/bin/env python3
"""启动 Polaris Agent Server。

用法: source venv/bin/activate && python run_server.py

Agent Server 启动后，所有通道（Chainlit、飞书、QQ 等）通过 HTTP 接入。
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8700, reload=True)
