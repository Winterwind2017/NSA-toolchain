"""nsa-mcp-hub 的 MCP 入口：六个 kit 聚合到一个 stdio 端点。"""

from __future__ import annotations

import sys

from ..hub import run_server


def main() -> int:
    return run_server()


if __name__ == "__main__":
    sys.exit(main())
