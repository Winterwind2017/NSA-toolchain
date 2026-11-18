#!/usr/bin/env python3
"""一条命令跑完离线质量门（不需要 AutoCAD）。

    python tools/parity_scan.py          # 只看不通过项，返回码 = 不通过数
    python tools/parity_scan.py --json   # 机器可读

检查四件事（都来自"说清楚才发布"的原则）：

1. **实现 ⊆ verified**：内核实现了但 registry 没标 verified 的能力（负例除外）。
2. **verified ⊆ 实现**：registry 标了 verified 但内核没有对应实现。
3. **dead 不许有实现**：标成"卡死"却偷偷实现了，说明结论过期。
4. **程序化路径不得用弹对话框的命令**（吸收自 CADCraft 的
   "programmatic calls never open dialogs"）：`NETLOAD` 实测会弹模态框把
   SendCommand 挂死；`-LAYERSTATE` 会卡在提示符；`PUBLISH` 会阻塞。
   我们在 build 层扫这些字面量，出现即不通过（除非显式列入豁免并写理由）。

CI 用法：`python tools/parity_scan.py`，返回码非 0 即失败。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps, registry                       # noqa: E402

BUILD_DIR = os.path.join(ROOT, "src", "acadkit", "build")

# 弹对话框 / 会卡提示符的命令：程序化路径一律不许出现
FORBIDDEN_COMMANDS = {
    "NETLOAD": "会弹模态文件对话框，SendCommand 永久阻塞（实测 2026-11-18）",
    "-LAYERSTATE": "动过图层表后 Save 永久卡在命令提示符（实测 2026-10-21）",
    "LAYERSTATE": "同上；命名图层状态改走 layer.state（.NET 通道）",
    "PUBLISH": "-PUBLISH 在双文档下阻塞",
}
# 允许出现的文件（豁免需写理由）
EXEMPT_FILES: Dict[str, str] = {}


def scan_forbidden() -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    if not os.path.isdir(BUILD_DIR):
        return hits
    for name in sorted(os.listdir(BUILD_DIR)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(BUILD_DIR, name)
        rel = os.path.relpath(path, ROOT)
        if rel in EXEMPT_FILES:
            continue
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                code = line.split("#", 1)[0]
                for cmd, why in FORBIDDEN_COMMANDS.items():
                    if re.search(r'["\'][^"\']*\b%s\b' % re.escape(cmd), code):
                        hits.append({"file": rel, "line": lineno, "command": cmd,
                                     "why": why, "text": line.strip()[:120]})
    return hits


def scan_registry() -> Dict[str, Any]:
    data = registry.load()
    verified = {c["id"] for c in data["capabilities"] if c.get("status") == "verified"}
    dead = {c["id"] for c in data["capabilities"] if c.get("status") == "dead"}
    impl = set(caps.implemented_ids())
    negative = {c.id for c in caps.CAPS
                if getattr(c, "is_negative", False)
                or getattr(c, "expect", "pass") != "pass"
                or "负例" in str(getattr(c, "level", ""))}

    return {
        "implemented_not_verified": sorted(impl - verified - negative),
        "verified_not_implemented": sorted(verified - impl - negative),
        "dead_but_implemented": sorted(dead & impl),
        "counts": {"registry": len(data["capabilities"]), "verified": len(verified),
                   "dead": len(dead), "implemented": len(impl)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="离线质量门")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    reg = scan_registry()
    forbidden = scan_forbidden()
    problems = (len(reg["implemented_not_verified"]) + len(reg["verified_not_implemented"])
                + len(reg["dead_but_implemented"]) + len(forbidden))

    payload = {"registry": reg, "forbidden_commands": forbidden, "problems": problems}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return problems

    c = reg["counts"]
    print("registry %d 条（verified %d / dead %d），内核实现 %d 条"
          % (c["registry"], c["verified"], c["dead"], c["implemented"]))
    for key, label in (("implemented_not_verified", "实现了但没标 verified（含负例请忽略）"),
                       ("verified_not_implemented", "标了 verified 但没实现"),
                       ("dead_but_implemented", "标了 dead 却有实现（结论过期）")):
        if reg[key]:
            print("  ✗ %s：%s" % (label, ", ".join(reg[key])))
    if forbidden:
        print("  ✗ 程序化路径出现弹框/阻塞命令：")
        for h in forbidden:
            print("     %s:%d  %s  —— %s" % (h["file"], h["line"], h["command"], h["why"]))
    if problems == 0:
        print("  ✓ 全部通过")
    else:
        print("合计 %d 项不通过" % problems)
    return problems


if __name__ == "__main__":
    sys.exit(main())
