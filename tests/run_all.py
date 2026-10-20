"""tests/run_all.py —— 统一真机回归 runner

把仓库自带的 7 个真机套件按顺序跑一遍，输出表格 + 可选 JSON。

为什么用**子进程**而不是直接调函数：

* 每个套件自己做 `CloseAllDocuments(True)`，单独进程才不会互相污染文档状态；
* SolidWorks 崩一次只毁一个套件，runner 仍能跑完并如实报告；
* `stdin=DEVNULL` 是硬要求（否则 SolidWorks 报错弹窗会把调用挂到超时）。

用法：

    python tests/run_all.py              # 全跑
    python tests/run_all.py --only drawing,balloon
    python tests/run_all.py --json out.json
    python tests/run_all.py --list

套件清单里 `selftest` / `mcp_smoke` 不需要真实建模，跑得很快，所以放最前面当"冒烟门"。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 夹具（测试用的 3D 文件）所在目录；不在则相关套件会自己报错
SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def _suites() -> list[dict]:
    scripts = {
        "selftest": None,                      # 用 -m swkit.cli.main selftest
        "mcp_smoke": "mcp_smoke.py",
        "live": "live_check.py",
        "part": "part_check.py",
        "sketch": "sketch_check.py",
        "sketch_ops": "sketch_ops_check.py",
        "inspect": "inspect_check.py",
        "asm_state": "asm_state_check.py",
        "features": "features_check.py",
        "io": "io_check.py",
        "doc_ops": "doc_ops_check.py",
        "drawing_extra": "drawing_extra_check.py",
        "sheet_metal": "sheet_metal_check.py",
        "config_io": "config_io_check.py",
        "view_measure": "view_measure_check.py",
        "equations": "equations_check.py",
        "sketch_edit": "sketch_edit_check.py",
        "bodies": "bodies_check.py",
        "surfaces": "surfaces_check.py",
        "cut": "cut_check.py",
        "analysis": "analysis_check.py",
        "dimxpert": "dimxpert_check.py",
        "flow": "flow_check.py",
        "draft": "draft_check.py",
        "flange_probe": "flange_probe_check.py",
        "draft_read": "draft_read_check.py",
        "drawing_views": "drawing_views_check.py",
        "asm_ops": "asm_ops_check.py",
        "drawing": "drawing_check.py",
        "balloon": "balloon_check.py",
    }
    return [{"name": name, "script": script} for name, script in scripts.items()]


def _cmd(suite: dict) -> list[str]:
    py = sys.executable
    if suite["script"] is None:
        return [py, "-m", "swkit.cli.main", "selftest"]
    return [py, os.path.join(HERE, suite["script"])]


def _needs_fixtures(suite: dict) -> bool:
    return suite["script"] not in (None, "mcp_smoke.py")


def _child_env() -> dict:
    """子进程环境：**显式**把 src 加进 PYTHONPATH。

    踩过：以前靠父 shell 里手工设 PYTHONPATH 才跑通；一旦不带环境变量直接调，
    `selftest` 就报 `No module named 'swkit'`。
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    src = os.path.join(ROOT, "src")
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if src not in parts:
        parts.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


_RPC_HINTS = ("RPC 服务器不可用", "RPC server is unavailable", "-2147023174")


def run_suite(suite: dict, timeout: float, retries: int = 1) -> dict:
    """跑一个套件；遇到 **RPC 掉线**（SolidWorks 长跑后被拖挂）自动重试。

    实测：15 套件连跑时 `live` 曾整段失败于
    `com_error (-2147023174, 'RPC 服务器不可用')`，复跑即 PASS——是 SW 累倒，
    不是代码回归。这里对它做一次重试，避免把环境抖动当成回归失败。
    """
    result = _run_once(suite, timeout)
    for _ in range(retries):
        blob = (result.get("output") or "") + (result.get("stderr") or "")
        if result.get("ok") or not any(h in blob for h in _RPC_HINTS):
            break
        result = _run_once(suite, timeout)
        result["retried_rpc"] = True
    return result


def _run_once(suite: dict, timeout: float) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(
            _cmd(suite), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
            cwd=ROOT, env=_child_env(),
        )
        out, err, rc = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        out, err, rc = "", "超时（%.0fs）" % timeout, -9
    elapsed = round(time.time() - started, 1)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines)
                    if "合计" in ln or "判定" in ln or "球标" in ln or "气球" in ln
                    or "ok=True" in ln or "通过" in ln), "")
    return {
        "suite": suite["name"],
        "rc": rc,
        "ok": rc == 0,
        "elapsed_s": elapsed,
        "summary": summary.strip()[:160],
        "tail": "\n".join(lines[-6:]),
        "stderr_tail": (err or "").strip().splitlines()[-3:] if err.strip() else [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的套件名")
    ap.add_argument("--json", default="", help="把结果写到该 JSON 文件")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    suites = _suites()
    if args.list:
        for s in suites:
            print("%-10s %s" % (s["name"], s["script"] or "-m swkit.cli.main selftest"))
        return 0
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        suites = [s for s in suites if s["name"] in wanted]
        if not suites:
            print("没有匹配的套件：%s" % args.only)
            return 2

    missing = [s["name"] for s in suites if _needs_fixtures(s) and not os.path.isdir(SIM)]
    if missing:
        print("警告：夹具目录不存在 %s（这些套件会失败）：%s" % (SIM, ", ".join(missing)))

    results = []
    print("=" * 88)
    for suite in suites:
        res = run_suite(suite, args.timeout)
        results.append(res)
        print("%-10s %-4s %6.1fs  %s"
              % (res["suite"], "OK" if res["ok"] else "FAIL", res["elapsed_s"],
                 res["summary"]))

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print("=" * 88)
    print("合计 %d 个套件，通过 %d，失败 %d，总耗时 %.1fs"
          % (total, passed, total - passed, sum(r["elapsed_s"] for r in results)))

    failed = [r for r in results if not r["ok"]]
    for r in failed:
        print("\n--- %s 失败（rc=%s）---" % (r["suite"], r["rc"]))
        print(r["tail"] or "(无输出)")
        for line in r["stderr_tail"]:
            print("stderr:", line)

    if args.json:
        payload = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "passed": passed, "total": total, "results": results}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("\n已写：%s" % args.json)
    return 0 if passed == total else 4


if __name__ == "__main__":
    raise SystemExit(main())
