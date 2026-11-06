"""eplan MCP 服务器入口（代理 CAD_SERVERS_HOME 的 EPLAN 2.9 MCP）。

    python -m nsa_mcp_hub.servers.eplan_mcp
"""

from __future__ import annotations

import os
import sys
import tempfile

from ..adapters.eplan_mcp import build_kit
from ..server import run_server


def main() -> int:
    kit = build_kit()
    kit.lock_path = os.path.join(tempfile.gettempdir(), "nsa-mcp-hub-%s.lock" % kit.key)
    kit.install_test_tools()
    return run_server(kit)


if __name__ == "__main__":
    sys.exit(main())
