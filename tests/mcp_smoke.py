"""最小 MCP stdio 客户端：给内核做端到端验收用（不依赖任何第三方包）。

用法：
    python tests/mcp_smoke.py <module> [tool ...]

    python tests/mcp_smoke.py nsa_mcp_hub.servers.nx_mcp nx_status nx_selftest
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Client:
    def __init__(self, module: str):
        env = dict(os.environ)
        env["PYTHONPATH"] = ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", module],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env, cwd=ROOT)
        self.next_id = 0

    def send(self, payload: dict) -> None:
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError("服务器无响应（退出码 %s）\n%s" % (self.proc.poll(), err))
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method,
                   "params": params or {}})
        msg = self.read()
        if "error" in msg:
            raise RuntimeError("RPC 错误：%s" % json.dumps(msg["error"], ensure_ascii=False))
        return msg["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:                              # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:                              # noqa: BLE001
            self.proc.kill()


def main(argv: list) -> int:
    module = argv[0]
    wanted = argv[1:]
    c = Client(module)
    try:
        init = c.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nsa-mcp-hub-smoke", "version": "0"},
        })
        print("initialize →", json.dumps(init, ensure_ascii=False)[:400])
        c.notify("notifications/initialized")

        listing = c.request("tools/list")
        tools = listing["tools"]
        print("\ntools/list → %d 个工具" % len(tools))
        for t in tools:
            print("  %-24s %s" % (t["name"], t["description"][:60]))

        failed = 0
        for name in wanted:
            print("\n=== tools/call %s ===" % name)
            res = c.request("tools/call", {"name": name, "arguments": {}})
            structured = res.get("structuredContent") or {}
            print(json.dumps(structured, ensure_ascii=False, indent=1)[:1800])
            if res.get("isError"):
                failed += 1
                print("  !! isError=true")
        return 1 if failed else 0
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
