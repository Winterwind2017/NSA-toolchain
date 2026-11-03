"""ug MCP 服务器入口（代理 CAD-Agent-Hub 的 Siemens NX MCP）。

    python -m nsa_mcp_hub.servers.ug_mcp
"""

from __future__ import annotations

import os
import sys
import tempfile

from ..adapters.ug_mcp import build_kit
from ..server import run_server


def main() -> int:
    kit = build_kit()
    kit.lock_path = os.path.join(tempfile.gettempdir(), "nsa-mcp-hub-%s.lock" % kit.key)
    kit.install_test_tools()
    return run_server(kit)


if __name__ == "__main__":
    sys.exit(main())
