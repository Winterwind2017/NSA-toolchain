"""acadkit MCP 服务器入口。

    python -m kitmcp.servers.acad_mcp
"""

from __future__ import annotations

import os
import os
import tempfile

import faulthandler
import os
import sys

from ..adapters.acadkit_adapter import build_kit
from ..server import run_server


def main() -> int:
    # KITMCP_DUMP_STACKS=30 → 每 30 s 把全部线程栈打到 stderr（排查"卡住"用）
    _every = os.environ.get("KITMCP_DUMP_STACKS")
    if _every:
        faulthandler.dump_traceback_later(int(float(_every)), repeat=True)
    kit = build_kit()
    # 跨进程单飞：DSH 与命令行同时驱动同一 kit 时靠文件锁互斥
    kit.lock_path = os.path.join(tempfile.gettempdir(), "kitmcp-%s.lock" % kit.key)
    kit.install_test_tools()
    return run_server(kit)


if __name__ == "__main__":
    sys.exit(main())
