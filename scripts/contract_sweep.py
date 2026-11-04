#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""契约扫描：把每个工具都调一次，检查它有没有守统一契约。

分三层，互不代替：

* **C0 schema**（100% 可达，不执行）：每个工具都声明了名字、描述、可解析的
  `inputSchema`，且 required 字段都在 properties 里。这层纯静态，零风险。
* **C1 invoke**（真调）：读类工具用 schema 生成的最小参数真调；写类工具用
  **故意非法的参数**（`__contract_probe__`）触发参数校验路径，不落任何真实改动；
  危险工具永不执行。判据只有一条——**返回必须是统一契约信封**
  （`ok` 是 bool、`reads` 是 dict 或缺失、`errors` 是 list 或缺失），
  且 ok=False 时必须给出证据（拒绝不许静默）。
* **C2 gated**：明确记录"没执行"的工具与原因（app 在跑 / 危险 / 超时）。

用法：
    python scripts/contract_sweep.py                    # 只跑 C0 + 读类 C1
    python scripts/contract_sweep.py --kit eplan,catia   # 指定 kit
    python scripts/contract_sweep.py --allow-write-probes  # 写类也发非法参数探针
    python scripts/contract_sweep.py --write              # 写报告到 _runs/
退出码：C0 有失败 → 1；C1 有契约违规 → 1；否则 0。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))

READ_HINT = re.compile(
    r"(list|get|inspect|query|status|info|health|caps|selftest|ping|version|catalog|"
    r"discover|read|tree|devices|projects|pages|inventory|search|plan|measure|bbox|"
    r"count|faces|edges|validate|check|preflight|summary|meta|symbols|rows|stats|"
    r"doctor|hcp|crossref|_il$|registry|commands|documents|graph|compare|diff|"
    r"source|files|disasm|bytes|recall|strings|names|help|schema|config|"
    r"topo|topology|geometry|work_part)", re.I)
# 宿主没开时也能安全执行、且能立刻给出结论的读类工具（不会卡在 attach 上）
OFFLINE_SAFE = re.compile(
    r"(status|caps|capabilities|selftest|ping|version|commands|help|doctor|registry|"
    r"catalog|discover|list_caps|list_documents|tool_catalog)", re.I)

DANGER = re.compile(
    r"(delete|remove|uninstall|close_all|_stop$|_stop_|format|purge|reboot|install_|"
    r"download|erase|kill|shutdown|clear_selection|online_download)", re.I)

# 这些 kit 的宿主程序装了但可能没开：写类探针一律不发，避免把它们拉起来
# 这两个 kit 的写类工具在宿主缺失时**不可能产生副作用**，所以默认就发非法参数探针：
#   * catia：所有写工具都要求已有 CATPart/CATProduct，没有就拒绝；
#   * eplan：写操作要 profile=trial + 实例 trial 标记 + 精确构建号，三缺一即拒。
# 其余 kit 的写工具可能**把宿主拉起来**（sw 的 COM Dispatch、gx/acad/codesys 的
# run_capability），所以默认不发探针，需要显式 --allow-write-probes 并自行确保静态。
SAFE_WRITE_PROBE_KITS = {"catia", "eplan"}

APP_PROCESS = {
    "sw": ["SLDWORKS"], "acad": ["acad"], "nx": ["ugraf"], "ug": ["ugraf"],
    "catia": ["CNEXT"], "codesys": ["CODESYS"], "autoshop": ["AutoShop"],
    "gx": ["GXWorks3", "GXW3"], "eplan": ["EPLAN"],
}


def processes_running(names: list[str]) -> list[str]:
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=60).stdout
    except Exception:                              # noqa: BLE001
        return []
    low = out.lower()
    return [name for name in names if ("%s.exe" % name.lower()) in low]


def minimal_value(schema: dict, *, bogus: bool = False):
    """按 JSON Schema 造一个最小合法值；bogus=True 时故意给非法值。"""
    if not isinstance(schema, dict):
        return None if bogus else None
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = kind[0] if kind else None
    if kind == "string":
        return "__contract_probe__" if bogus else ""
    if kind in ("number", "integer"):
        if bogus:
            return "__contract_probe__"
        value = schema.get("default", schema.get("minimum", 0))
        return 0 if kind == "integer" else float(value or 0)
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if kind is None:
        return "__contract_probe__" if bogus else None
    return None


def build_args(schema: dict, *, bogus: bool) -> dict:
    """只给 required 字段，其余留空——这是"最小可调用"的定义。"""
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or []
    args = {}
    for name in required:
        args[name] = minimal_value(props.get(name) or {}, bogus=bogus)
    return args


def schema_problems(tool: dict) -> list[str]:
    """C0：静态检查。"""
    problems = []
    name = tool.get("name")
    if not name or not isinstance(name, str):
        problems.append("缺 name")
    if not (tool.get("description") or "").strip():
        problems.append("缺 description")
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        problems.append("inputSchema 不是对象")
        return problems
    if schema.get("type") != "object":
        problems.append("inputSchema.type 不是 object")
    props = schema.get("properties")
    if props is not None and not isinstance(props, dict):
        problems.append("properties 不是对象")
    required = schema.get("required") or []
    if props is not None:
        for field in required:
            if field not in props:
                problems.append("required 里的 %r 不在 properties" % field)
    return problems


def check_envelope(payload) -> list[str]:
    """C1 判据：统一契约信封。"""
    if not isinstance(payload, dict):
        return ["返回不是对象：%r" % (type(payload).__name__,)]
    problems = []
    if not isinstance(payload.get("ok"), bool):
        problems.append("缺 ok(bool)")
    reads = payload.get("reads")
    if reads is not None and not isinstance(reads, dict):
        problems.append("reads 不是对象")
    errors = payload.get("errors")
    if errors is not None and not isinstance(errors, list):
        problems.append("errors 不是数组")
    checks = payload.get("checks")
    if checks is not None and not isinstance(checks, list):
        problems.append("checks 不是数组")
    # ok=False 必须有证据（拒绝不许静默）
    if payload.get("ok") is False:
        from nsa_mcp_hub.acceptance.harness import refusal_evidence
        if refusal_evidence(payload) is None:
            problems.append("ok=False 但无任何错误证据（静默失败）")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="工具契约扫描（C0 静态 / C1 真调）")
    parser.add_argument("--kit", default="", help="逗号分隔，默认全部")
    parser.add_argument("--timeout", type=float, default=30.0, help="单工具超时秒数")
    parser.add_argument("--allow-write-probes", action="store_true",
                        help="给写类工具发非法参数探针（默认只跑读类）")
    parser.add_argument("--write", action="store_true", help="把报告写到 _runs/")
    args = parser.parse_args()

    from nsa_mcp_hub.acceptance.harness import McpClient
    from nsa_mcp_hub.hub import KITS

    wanted = {k.strip() for k in args.kit.split(",") if k.strip()}
    started = time.strftime("%Y%m%d-%H%M%S")
    report = {"when": started, "kits": []}
    grand = Counter()
    violations = 0

    for kit, module in KITS.items():
        if wanted and kit not in wanted:
            continue
        running = processes_running(APP_PROCESS.get(kit, []))
        client = McpClient(module)
        try:
            tools = client.tools()
        finally:
            client.close()

        entry = {"kit": kit, "tools": len(tools), "app_running": running,
                 "c0_failed": [], "c1": [], "gated": []}
        c1_by_tool = {tool.get("name"): None for tool in tools}

        # ── C0 schema ──
        for tool in tools:
            problems = schema_problems(tool)
            if problems:
                entry["c0_failed"].append({"tool": tool.get("name"), "problems": problems})

        # ── 逐个执行 C1 ──
        client = McpClient(module)
        try:
            for tool in tools:
                name = tool.get("name")
                if not name:
                    continue
                if DANGER.search(name):
                    c1_by_tool[name] = {"verdict": "gated", "reason": "danger"}
                    entry["gated"].append({"tool": name, "reason": "danger"})
                    continue
                read_like = bool(READ_HINT.search(name))
                write_probe_allowed = (args.allow_write_probes
                                       or kit in SAFE_WRITE_PROBE_KITS)
                # 宿主没开时，非"离线安全"的读类工具会卡在 attach 上（实测
                # acad_projection_orthographic 就这样卡满 20 s）。这类直接标记
                # app_required，理由写清楚，不假装执行过。
                if read_like and not running and not OFFLINE_SAFE.search(name):
                    c1_by_tool[name] = {"verdict": "gated", "reason": "app_required"}
                    entry["gated"].append({"tool": name, "reason": "app_required"})
                    continue
                if not read_like and not write_probe_allowed:
                    c1_by_tool[name] = {"verdict": "gated", "reason": "write_not_probed"}
                    entry["gated"].append({"tool": name, "reason": "write_not_probed"})
                    continue
                if not read_like and running:
                    # 写类探针 + 宿主在跑 = 有真实副作用风险，宁可不动
                    c1_by_tool[name] = {"verdict": "gated", "reason": "app_running"}
                    entry["gated"].append({"tool": name, "reason": "app_running"})
                    continue

                schema = tool.get("inputSchema") or {}
                kwargs = build_args(schema, bogus=not read_like)
                t0 = time.time()
                box: dict = {}

                def _invoke(tool_name=name, tool_args=kwargs):
                    try:
                        box["payload"] = client.call(tool_name, tool_args)
                    except Exception as exc:                   # noqa: BLE001
                        box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])

                worker = threading.Thread(target=_invoke, daemon=True)
                worker.start()
                worker.join(args.timeout)
                if worker.is_alive():
                    # 卡住的工具：关掉整个 kit 进程重开，后面的工具继续跑
                    c1_by_tool[name] = {"verdict": "timeout", "ms": int((time.time() - t0) * 1000),
                                        "detail": "超过 %.0fs 未返回" % args.timeout}
                    try:
                        client.close()
                    except Exception:                          # noqa: BLE001
                        pass
                    client = McpClient(module)
                    print("     .. %-32s timeout(%.0fs)" % (name, args.timeout), flush=True)
                    continue
                if "error" in box:
                    c1_by_tool[name] = {"verdict": "error", "ms": int((time.time() - t0) * 1000),
                                        "detail": box["error"]}
                    print("     .. %-32s error" % name, flush=True)
                    continue
                payload = box["payload"]
                ms = int((time.time() - t0) * 1000)
                problems = check_envelope(payload)
                if problems:
                    violations += 1
                c1_by_tool[name] = {
                    "verdict": "contract_violation" if problems else "ok",
                    "ms": ms, "ok": payload.get("ok"),
                    "problems": problems, "args": kwargs,
                    "detail": (json.dumps(payload, ensure_ascii=False)[:160]
                               if problems else ""),
                }
        finally:
            client.close()

        entry["c1"] = [{"tool": name, **item} for name, item in c1_by_tool.items() if item]
        counts = Counter(item["verdict"] for item in c1_by_tool.values() if item)
        grand.update(counts)
        report["kits"].append(entry)

        print("\n=== %s：%d 个工具（宿主进程：%s）==="
              % (kit, len(tools), ", ".join(running) or "未运行"))
        print("   C0 静态：%d 失败 / %d" % (len(entry["c0_failed"]), len(tools)))
        print("   C1 执行：%s" % dict(counts))
        if entry["c0_failed"]:
            for item in entry["c0_failed"][:5]:
                print("     !! %-32s %s" % (item["tool"], ", ".join(item["problems"])))
        bad = [item for item in entry["c1"] if item["verdict"] != "ok"]
        for item in bad[:6]:
            print("     !! %-32s %s %s" % (item["tool"], item["verdict"],
                                           " ".join(item.get("problems") or [])))

    total_tools = sum(k["tools"] for k in report["kits"])
    c0_bad = sum(len(k["c0_failed"]) for k in report["kits"])
    print("\n" + "=" * 64)
    print("合计 %d 个工具｜C0 schema 失败 %d｜C1 %s"
          % (total_tools, c0_bad, dict(grand)))
    print("说明：gated 是「明确没执行」，不是通过；danger 永不执行。")

    if args.write:
        out = HUB / "_runs" / ("contract-sweep-%s.json" % started)
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("报告：%s" % out.relative_to(HUB))
    return 1 if (c0_bad or violations) else 0


if __name__ == "__main__":
    sys.exit(main())
