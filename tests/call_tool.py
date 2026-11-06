"""通用：通过 MCP 调任意工具。

    python tests/call_tool.py <module> <tool> '<json args>'
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_smoke import Client  # noqa: E402


def main(argv: list) -> int:
    module, tool = argv[0], argv[1]
    args = json.loads(argv[2]) if len(argv) > 2 else {}
    c = Client(module)
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "nsa-mcp-hub-call", "version": "0"}})
        c.notify("notifications/initialized")
        c.request("tools/list")
        print("调用 %s(%s) …" % (tool, json.dumps(args, ensure_ascii=False)))
        res = c.request("tools/call", {"name": tool, "arguments": args})
        payload = res.get("structuredContent") or {}
        print("\nok=%s  isError=%s  seconds=%s"
              % (payload.get("ok"), res.get("isError"), payload.get("seconds")))
        checks = payload.get("checks") or []
        if checks:
            print("\n判据 %d 条：" % len(checks))
            for chk in checks:
                key = chk.get("check") or chk.get("key") or "?"
                print("  %-24s got=%-16r %s"
                      % (key, chk.get("got"), "OK" if chk.get("ok") else "**FAIL**"))
        for rec in payload.get("results") or []:
            print("\n-- %s ok=%s %ss" % (rec.get("capability"), rec.get("ok"),
                                         rec.get("seconds")))
            if rec.get("detail"):
                det = json.dumps(rec["detail"], ensure_ascii=False)
                print("   detail: %s" % det[:400])
        if payload.get("reads"):
            print("\nreads: %s" % json.dumps(payload["reads"], ensure_ascii=False)[:700])
        if payload.get("errors"):
            print("\nerrors: %s" % payload["errors"])
        return 0 if payload.get("ok") else 1
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
