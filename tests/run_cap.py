"""端到端：通过 MCP 调 nx_run_capability 跑指定能力。

    python tests/run_cap.py solid.block solid.move_body
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_smoke import Client  # noqa: E402


def main(argv: list) -> int:
    ids = argv or ["solid.block"]
    c = Client("nsa_mcp_hub.servers.nx_mcp")
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "nsa-mcp-hub-run-cap", "version": "0"}})
        c.notify("notifications/initialized")
        c.request("tools/list")
        print("跑能力：%s" % ids)
        res = c.request("tools/call", {"name": "nx_run_capability",
                                       "arguments": {"ids": ids, "timeout_s": 900}})
        payload = res.get("structuredContent") or {}
        print("\nok=%s  passed=%s/%s  session=%.1fs  rc=%s  timed_out=%s"
              % (payload.get("ok"), (payload.get("reads") or {}).get("passed"),
                 (payload.get("reads") or {}).get("total"),
                 (payload.get("seconds") or 0.0),
                 (payload.get("reads") or {}).get("returncode"),
                 (payload.get("reads") or {}).get("timed_out")))
        for rec in payload.get("results") or []:
            print("\n--- %s  ok=%s  %.1fs" % (rec["capability"], rec["ok"], rec.get("seconds") or 0))
            for chk in rec.get("checks") or []:
                print("    %-22s got=%-14r want=%-24r %s"
                      % (chk.get("check"), chk.get("got"), chk.get("want"),
                         "OK" if chk.get("ok") else "**FAIL**"))
            for err in rec.get("errors") or []:
                print("    error: %s" % err)
        if payload.get("errors"):
            print("\n顶层 errors: %s" % payload["errors"][:2])
        return 0 if payload.get("ok") else 1
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
