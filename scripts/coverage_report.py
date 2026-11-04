#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验收覆盖度报告：每个 kit 有多少工具、有多少被验收用例真的调过。

数字来源（都是实打实的，不估）：

* 工具数：起一个 kit 的 MCP 进程，问 `tools/list`；
* 用例数与被覆盖的工具：直接读 `nsa_mcp_hub.acceptance.cases.KITS`（同一份注册表，
  不多算也不少算）。

用法：
    python scripts/coverage_report.py                 # 打表
    python scripts/coverage_report.py --write         # 同时写 docs/acceptance-coverage.md
    python scripts/coverage_report.py --only sw,eplan # 只看几个 kit
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))


def kit_modules() -> dict[str, str]:
    """从 hub 的 KITS 注册表取 kit → module。"""
    from nsa_mcp_hub.hub import KITS
    return dict(KITS)


def kit_cases() -> dict[str, list[dict]]:
    """验收注册表是 kit → {module, setup, cases}；这里只取 cases。"""
    from nsa_mcp_hub.acceptance import cases
    return {kit: list(spec.get("cases") or [])
            for kit, spec in cases.KITS.items()}


def tools_of(kit: str, module: str) -> list[str]:
    from nsa_mcp_hub.acceptance.harness import McpClient
    client = McpClient(module)
    try:
        return [str(t.get("name")) for t in client.tools()]
    finally:
        client.close()


def cases_of() -> dict[str, list[dict]]:
    return kit_cases()


def main() -> int:
    parser = argparse.ArgumentParser(description="验收覆盖度报告")
    parser.add_argument("--write", action="store_true", help="写 docs/acceptance-coverage.md")
    parser.add_argument("--only", default="", help="逗号分隔的 kit 名")
    args = parser.parse_args()

    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    modules = kit_modules()
    cases = cases_of()

    rows = []
    total_tools = total_covered = total_cases = 0
    for kit, module in modules.items():
        if wanted and kit not in wanted:
            continue
        try:
            tools = tools_of(kit, module)
        except Exception as exc:                       # noqa: BLE001
            print("!! %s 起不来：%s" % (kit, exc))
            continue
        items = cases.get(kit, [])
        # 有的用例走 call 钩子（多步），没有 tool 字段——单独计，不算未覆盖
        single = [item for item in items if item.get("tool")]
        referenced = {item["tool"] for item in single if item["tool"] in tools}
        extra = sorted({item["tool"] for item in single if item["tool"] not in tools})
        total_tools += len(tools)
        total_covered += len(referenced)
        total_cases += len(items)
        rows.append({
            "kit": kit, "tools": len(tools), "cases": len(items),
            "covered": len(referenced),
            "pct": (100.0 * len(referenced) / len(tools)) if tools else 0.0,
            "multi_step": len(items) - len(single),
            "skipped": sum(1 for item in items if item.get("skip_if")),
            "no_setup": sum(1 for item in items if item.get("no_setup")),
            "unknown_tools": extra,
            "uncovered": [t for t in tools if t not in referenced],
        })

    print("| kit | 工具数 | 用例数 | 覆盖到的工具 | 覆盖率 | skip_if | no_setup |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        print("| **%s** | %d | %d | %d | %.1f%% | %d | %d |"
              % (row["kit"], row["tools"], row["cases"], row["covered"], row["pct"],
                 row["skipped"], row["no_setup"]))
    pct = (100.0 * total_covered / total_tools) if total_tools else 0.0
    print("| **合计** | %d | %d | %d | **%.1f%%** | | |"
          % (total_tools, total_cases, total_covered, pct))

    for row in rows:
        if row["unknown_tools"]:
            print("\n!! %s 的用例引用了不存在的工具：%s" % (row["kit"], row["unknown_tools"]))
        if row["uncovered"]:
            head = ", ".join(row["uncovered"][:8])
            more = " …" if len(row["uncovered"]) > 8 else ""
            print("\n%s 未覆盖（%d）：%s%s"
                  % (row["kit"], len(row["uncovered"]), head, more))

    if args.write:
        out = HUB / "docs" / "acceptance-coverage.md"
        lines = ["# 验收覆盖度（自动生成，别手改）",
                 "",
                 "由 `python scripts\\coverage_report.py --write` 生成。工具数来自真实 `tools/list`，",
                 "用例来自 `nsa_mcp_hub.acceptance.cases.KITS`。",
                 "",
                 "| kit | 工具数 | 用例数 | 覆盖到的工具 | 覆盖率 | skip_if | no_setup |",
                 "|---|---|---|---|---|---|---|"]
        for row in rows:
            lines.append("| **%s** | %d | %d | %d | %.1f%% | %d | %d |"
                         % (row["kit"], row["tools"], row["cases"], row["covered"],
                            row["pct"], row["skipped"], row["no_setup"]))
        lines.append("| **合计** | %d | %d | %d | **%.1f%%** | | |"
                     % (total_tools, total_cases, total_covered, pct))
        lines += ["", "## 未覆盖的工具", ""]
        for row in rows:
            if row["uncovered"]:
                lines.append("### %s（%d / %d 未覆盖）" % (row["kit"], len(row["uncovered"]), row["tools"]))
                lines.append("")
                for name in row["uncovered"]:
                    lines.append("- `%s`" % name)
                lines.append("")
        out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        print("\n已写 %s" % out.relative_to(HUB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
