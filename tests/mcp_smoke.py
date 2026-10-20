"""tests/mcp_smoke.py —— MCP stdio 握手冒烟

目的：证明 `swkit-mcp` 真的能作为 MCP server 起来并响应 `initialize`，
而不是"模块能 import"就算数。

做法：用当前解释器起 `python -m swkit.mcp.server`，往其 stdin 写一条 MCP `initialize`
请求（stdio 传输为**换行分隔 JSON**），读回第一行并解析。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src")
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-m", "swkit.mcp.server"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=env)
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "swkit-smoke", "version": "0"},
        },
    }
    try:
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        deadline = time.time() + 25
        line = ""
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line.strip():
                break
        if not line.strip():
            err = (proc.stderr.read() if proc.stderr else "")[:600]
            print("FAIL：25s 内没有收到响应\nstderr=%s" % err)
            return 4
        msg = json.loads(line)
        result = msg.get("result") or {}
        info = result.get("serverInfo") or {}
        print("OK：serverInfo=%r protocolVersion=%r"
              % (info, result.get("protocolVersion")))
        return 0 if info.get("name") == "swkit" else 4
    except Exception as exc:                       # noqa: BLE001
        print("FAIL：%s: %s" % (type(exc).__name__, exc))
        return 4
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
