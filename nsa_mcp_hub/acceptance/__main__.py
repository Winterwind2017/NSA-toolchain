"""命令行：python -m nsa_mcp_hub.acceptance --kit sw [--kit nx ...] [--only id1,id2]

退出码：全部通过 0，否则 1。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .cases import KITS
from .harness import print_summary, run_kit
from .sweep import coverage, sweep_cases

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="nsa_mcp_hub.acceptance",
                                     description="用 MCP 真机跑各 kit 的固定验收用例")
    parser.add_argument("--kit", action="append", choices=sorted(KITS),
                        help="要跑的 kit，可重复；默认全部可用 kit")
    parser.add_argument("--only", default="",
                        help="只跑这些用例 id（逗号分隔）")
    parser.add_argument("--report", default="",
                        help="把 JSON 报告写到该路径")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--sweep", action="store_true",
                        help="能力扫描模式：把每条能力当成一条用例跑（判据用能力自带的 judge）")
    parser.add_argument("--sweep-max", type=int, default=0,
                        help="每个 kit 最多扫多少条（0 = 全部）")
    args = parser.parse_args(argv)

    kits = args.kit or ["sw", "acad", "nx", "gx", "codesys", "autoshop"]
    only = [x.strip() for x in args.only.split(",") if x.strip()] or None

    started = time.time()
    summaries = []
    for key in kits:
        spec = dict(KITS[key])
        if args.sweep:
            generated = sweep_cases(key, args.sweep_max)
            if not generated:
                print("\n=== %s：没有可扫描的能力（跳过）===" % key, flush=True)
                continue
            spec["cases"] = generated
            cov = coverage(key)
            print("\n=== %s 能力扫描：%d 条用例（能力 %d，有工具 %d）==="
                  % (key, len(generated), cov["caps"], cov["with_tool"]), flush=True)
        else:
            print("\n=== %s（%s）===" % (key, spec["module"]), flush=True)
        summary = run_kit(key, spec, only=only, verbose=not args.quiet)
        print_summary(summary)
        summaries.append(summary)

    total = sum(s["total"] for s in summaries)
    passed = sum(s["passed"] for s in summaries)
    skipped = sum(s.get("skipped", 0) for s in summaries)
    failed = [r for s in summaries for r in s["results"]
              if r["verdict"] in ("FAIL", "ERROR")]
    print("\n总计：%d/%d 通过%s，用时 %.1fs"
          % (passed, total, ("（%d 跳过）" % skipped) if skipped else "",
             time.time() - started))
    if failed:
        print("未通过：")
        for r in failed:
            print("  - [%s] %s %s" % (r["kit"], r["id"], r["detail"]))

    report_path = args.report or os.path.join(
        ROOT, "_runs", "acceptance-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"when": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "kits": summaries, "passed": passed, "total": total},
                  fh, ensure_ascii=False, indent=1)
    print("报告：%s" % report_path)
    return 0 if not failed and total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
