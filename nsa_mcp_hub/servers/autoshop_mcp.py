"""autoshopkit MCP 服务器入口。

    python -m nsa_mcp_hub.servers.autoshop_mcp
"""

from __future__ import annotations

import os
import os
import tempfile

import sys

from ..adapters.autoshopkit_adapter import build_kit
from ..server import run_server


def main() -> int:
    kit = build_kit()
    # 跨进程单飞：DSH 与命令行同时驱动同一 kit 时靠文件锁互斥
    kit.lock_path = os.path.join(tempfile.gettempdir(), "nsa-mcp-hub-%s.lock" % kit.key)
    kit.install_test_tools()
    return run_server(kit)


if __name__ == "__main__":
    sys.exit(main())
