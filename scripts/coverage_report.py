#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""覆盖度报告 v2：三列分开算，绝不混着报。

| 列 | 含义 | 数据来源 |
|---|---|---|
| **验收覆盖** | 被验收用例引用到的工具（含"明确拒绝"模式） | `acceptance.cases.KITS` |
| **契约覆盖** | 契约扫描里真的执行过、且返回合契约的工具 | `_runs/contract-sweep-*.json` |
| **快乐路径** | 验收里 verdict=PASS 且不是拒绝模式，工具被真的调用成功 | `_runs/acceptance-*.json` |
| **合并** | 验收 ∪ 契约 | 上面两者 |

用法：
    python scripts/coverage_report.py --write
    python scripts/coverage_report.py --sweep <json> --accept <json>
    python scripts/coverage_report.py --only sw,eplan
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))
RUNS = HUB / "_runs"


def latest(pattern: str) -> Path | None:
    files = sorted(RUNS.glob(pattern))
    return files[-1] if files else None


def kit_modules() -> dict[str, str]:
    from nsa_mcp_hub.hub import KITS
    return dict(KITS)


def tools_of(module: str) -> list[str]:
    from nsa_mcp_hub.acceptance.harness import McpClient
    client = McpClient(module)
    try:
        return [str(t.get("name")) for t in client.tools()]
    finally:
        client.close()


def case_tools() -> dict[str, dict]:
    """kit → {tool: case_id}。剧本用例（tool=None）不在这里，由运行报告补。"""
    from nsa_mcp_hub.acceptance import cases
    out: dict[str, dict] = {}
    for kit, spec in cases.KITS.items():
        mapping = {}
        for item in spec.get("cases") or []:
            tool = item.get("tool")
            if tool:
                mapping.setdefault(tool, item["id"])
        out[kit] = mapping
    return out


def sweep_ok(path) -> dict[str, set[str]]:
    """契约覆盖取**所有**扫描报告的并集（分 kit 跑的多份报告要合起来看）。"""
    out: dict[str, set[str]] = {}
    paths = ([path] if isinstance(path, Path) else list(path or []))
    for item in paths:
        if item is None or not item.is_file():
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except Exception:                              # noqa: BLE001
            continue
        for entry in data.get("kits") or []:
            bucket = out.setdefault(entry.get("kit"), set())
            bucket.update(item2["tool"] for item2 in (entry.get("c1") or [])
                          if item2.get("verdict") == "ok")
    return out


def touched_tools(path) -> dict[str, set[str]]:
    """验收**真的调过**的工具（含剧本子步骤，不论通过与否）——用于"验收覆盖"列。"""
    out: dict[str, set[str]] = {}
    paths = ([path] if isinstance(path, Path) else list(path or []))
    for item in paths:
        if item is None or not item.is_file():
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except Exception:                              # noqa: BLE001
            continue
        for entry in data.get("kits") or []:
            bucket = out.setdefault(entry.get("kit"), set())
            for row in entry.get("results") or []:
                if row.get("tool"):
                    bucket.add(row["tool"])
                for name in row.get("covered_tools") or []:
                    bucket.add(name)
    return out


def happy_tools(path) -> dict[str, set[str]]:
    """快乐路径取**所有**验收报告的并集（一次跑只覆盖一部分 kit，并集才代表"曾经过"）。"""
    out: dict[str, set[str]] = {}
    paths = ([path] if isinstance(path, Path) else list(path or []))
    for item in paths:
        if item is None or not item.is_file():
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except Exception:                              # noqa: BLE001
            continue
        for entry in data.get("kits") or []:
            kit = entry.get("kit")
            tools: set[str] = out.setdefault(kit, set())
            for row in entry.get("results") or []:
                if row.get("verdict") != "PASS" or row.get("mode") == "refusal":
                    continue
                if row.get("tool"):
                    tools.add(row["tool"])
                for name in row.get("covered_tools") or []:
                    tools.add(name)
    return out


def _unused(path: Path | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if path is None or not path.is_file():
        return out
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data.get("kits") or []:
        kit = entry.get("kit")
        tools: set[str] = set()
        for row in entry.get("results") or []:
            if row.get("verdict") != "PASS" or row.get("mode") == "refusal":
                continue
            if row.get("tool"):
                tools.add(row["tool"])
            for name in row.get("covered_tools") or []:
                tools.add(name)
        out[kit] = tools
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="覆盖度报告 v2（验收 / 契约 / 快乐路径）")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--sweep", default="")
    parser.add_argument("--accept", default="")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    sweep_paths = ([Path(args.sweep)] if args.sweep
                   else sorted(RUNS.glob("contract-sweep-*.json")))
    accept_paths = ([Path(args.accept)] if args.accept
                    else sorted(RUNS.glob("acceptance-*.json")))
    sweep = sweep_ok(sweep_paths)
    happy = happy_tools(accept_paths)
    touched = touched_tools(accept_paths)
    cases = case_tools()

    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    rows = []
    total = {"tools": 0, "acc": 0, "c1": 0, "union": 0, "happy": 0}
    for kit, module in kit_modules().items():
        if wanted and kit not in wanted:
            continue
        try:
            tools = set(tools_of(module))
        except Exception as exc:                      # noqa: BLE001
            print("!! %s 起不来：%s" % (kit, exc))
            continue
        acc = (set(cases.get(kit, {})) | touched.get(kit, set())) & tools
        c1 = sweep.get(kit, set()) & tools
        union = acc | c1
        hp = happy.get(kit, set()) & tools
        rows.append({"kit": kit, "tools": len(tools), "acc": len(acc), "c1": len(c1),
                     "union": len(union), "happy": len(hp), "gated": len(tools - union)})
        for key, value in (("tools", len(tools)), ("acc", len(acc)), ("c1", len(c1)),
                           ("union", len(union)), ("happy", len(hp))):
            total[key] += value

    def pct(part: int) -> str:
        return "%.1f%%" % (100.0 * part / total["tools"]) if total["tools"] else "0%"

    def line(row: dict) -> str:
        share = 100.0 * row["union"] / row["tools"] if row["tools"] else 0.0
        return ("| **%s** | %d | %d | %d | %d (%.1f%%) | %d | %d |"
                % (row["kit"], row["tools"], row["acc"], row["c1"], row["union"],
                   share, row["happy"], row["gated"]))

    print("| kit | 工具 | 验收覆盖 | 契约覆盖 | 合并 | 快乐路径 | 未覆盖 |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        print(line(row))
    print("| **合计** | %d | %d | %d | %d (%s) | %d | %d |"
          % (total["tools"], total["acc"], total["c1"], total["union"],
             pct(total["union"]), total["happy"], total["tools"] - total["union"]))
    print("\n数据来源：")
    print("  契约扫描：%d 份（并集）" % len(sweep_paths))
    print("  验收报告：%d 份（并集）" % len(accept_paths))

    if args.write:
        out = HUB / "docs" / "acceptance-coverage.md"
        lines = [
            "# 覆盖度（自动生成，别手改）",
            "",
            "`python scripts\\coverage_report.py --write` 生成。**三列分开算，不混报**：",
            "",
            "- **验收覆盖**：验收用例引用到 + 剧本真的调过的工具（含「明确拒绝」模式）；",
            "- **契约覆盖**：契约扫描里真执行过、且返回合统一契约的工具；",
            "- **快乐路径**：验收判定 PASS 且不是拒绝模式、工具被真的调成功；",
            "- **合并**：验收 ∪ 契约；**未覆盖** = 三者都没碰到。",
            "",
            "| kit | 工具 | 验收覆盖 | 契约覆盖 | 合并 | 快乐路径 | 未覆盖 |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            lines.append(line(row))
        lines.append("| **合计** | %d | %d | %d | %d (%s) | %d | %d |"
                     % (total["tools"], total["acc"], total["c1"], total["union"],
                        pct(total["union"]), total["happy"], total["tools"] - total["union"]))
        lines += ["", "数据来源：", "",
                  "- 契约扫描：`_runs/contract-sweep-*.json` 共 %d 份（并集）" % len(sweep_paths),
                  "- 验收报告：`_runs/acceptance-*.json` 共 %d 份（并集）" % len(accept_paths),
                  "",
                  "## gated 是什么",
                  "",
                  "契约扫描里没执行的工具，原因记录在报告的 `gated` 数组里，只有四种：",
                  "",
                  "| 原因 | 含义 |",
                  "|---|---|",
                  "| `danger` | 危险工具（删/停/下载/卸载），永不执行 |",
                  "| `app_running` | 宿主正在跑，写探针有真实副作用 |",
                  "| `app_required` | 宿主没开，连读都会卡在 attach 上 |",
                  "| `write_not_probed` | 写类工具默认不发探针（可能把宿主拉起来） |",
                  "",
                  "要把这些计入覆盖，得按 kit 起宿主并用沙箱剧本执行——见 `docs/coverage-plan.md`。",
                  ""]
        out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        print("已写 %s" % out.relative_to(HUB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
