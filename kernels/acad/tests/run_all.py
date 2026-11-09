#!/usr/bin/env python3
"""run_all.py —— 一条命令跑完：离线测试 + 文档一致性 + 真机能力。

    python tests/run_all.py                 # 全量（真机约 6–8 分钟）
    python tests/run_all.py --skip-live     # 只跑离线（不需要 AutoCAD）
    python tests/run_all.py --only geom,dim # 只跑真机里的某些族

退出码：0 全绿 · 1 有失败 · 2 参数/环境错误
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


def run(label, cmd, timeout=None):
    print("\n" + "=" * 78)
    print("== %s" % label)
    print("=" * 78)
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT)
    dt = time.time() - t0
    print("-- %s：%s（%.1fs）" % (label, "PASS" if p.returncode == 0 else
                                 "FAIL(%d)" % p.returncode, dt))
    return p.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="acadkit 全量验收")
    ap.add_argument("--skip-live", action="store_true", help="只跑离线")
    ap.add_argument("--only", default=None, help="真机：族或 id，逗号分隔")
    ap.add_argument("--case-timeout", type=float, default=120.0)
    ap.add_argument("--keep", action="store_true", help="跑完不退出 AutoCAD")
    args = ap.parse_args(argv)

    results = {}
    results["offline"] = run("离线测试（pytest）",
                             [PY, "-m", "pytest", "tests", "-q"])
    results["docs"] = run("文档一致性（pytest）",
                          [PY, "-m", "pytest", "tests/test_docs.py", "-q"])
    results["counts"] = run("README 计数",
                            [PY, "tools/gen_readme_counts.py", "--check"])
    results["unsupported"] = run("UNSUPPORTED 状态",
                                 [PY, "tools/gen_unsupported.py", "--check"])
    if not args.skip_live:
        cmd = [PY, "-u", "tests/live_judges.py",
               "--case-timeout", str(args.case_timeout)]
        if args.only:
            cmd += ["--only", args.only]
        if args.keep:
            cmd.append("--keep")
        results["live"] = run("真机能力（全部）", cmd)

    print("\n" + "=" * 78)
    bad = {k: v for k, v in results.items() if v != 0}
    for k, v in results.items():
        print("  %-12s %s" % (k, "PASS" if v == 0 else "FAIL(%d)" % v))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
