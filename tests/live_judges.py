"""真机验收：跑 `caps` 里的能力（动作 + 判据 + 每例前后环境自检）。

    python tests/live_judges.py                 # 全部能力
    python tests/live_judges.py --only geom,dim # 按族或用例 id 过滤
    python tests/live_judges.py --keep          # 跑完不退出 AutoCAD

产出 `_scratch/judges_<时间戳>/results.json`（完整 checks/detail/raw）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps                                    # noqa: E402
from acadkit.core import com, env, launch                   # noqa: E402
from acadkit.judges.case import (CaseRunner, env_signature,  # noqa: E402
                                 finish)

MARK = {True: "PASS", False: "FAIL"}

# 看门狗：有些 AutoCAD 命令会停在提示符上等输入，SendCommand 永远不返回。
# 超时就**强杀 acad 并退出**（不是假装通过），把现场写进 TIMEOUT.txt。
_WATCH = {"deadline": 0.0, "case": None, "workdir": None}


def start_watchdog(per_case_s: float, workdir: str) -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                cid = _WATCH["case"]
                msg = ("用例 %s 超过 %.0fs 未返回 —— 大概率停在 AutoCAD 命令提示符上。"
                       "已强杀 acad.exe 并中止本轮。" % (cid, per_case_s))
                print("\n!! " + msg)
                sys.stdout.flush()
                try:
                    with open(os.path.join(workdir, "TIMEOUT.txt"), "w",
                              encoding="utf-8") as fh:
                        fh.write(msg + "\n")
                except Exception:                       # noqa: BLE001
                    pass
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"],
                               capture_output=True)
                os._exit(9)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    _WATCH["workdir"] = workdir


def print_table(results: List[Dict[str, Any]]) -> None:
    print("")
    print("%-12s %-30s %-7s %-5s %-5s %-7s %s"
          % ("族", "用例", "级别", "类型", "结果", "耗时", "失败项"))
    print("-" * 112)
    for r in results:
        failed = [k for k, v in (r.get("checks") or {}).items() if v is False]
        print("%-12s %-30s %-7s %-5s %-5s %6.1fs %s"
              % (r["family"], r["id"],
                 (caps.BY_ID.get(r["id"]).level if r["id"] in caps.BY_ID else "-"),
                 "负例" if r["negative"] else "正常",
                 MARK[bool(r["ok"])], r.get("duration_s") or 0.0,
                 ", ".join(failed) if failed else "-"))
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print("-" * 112)
    print("合计 %d 例：通过 %d / 失败 %d" % (total, passed, total - passed))
    env_total = sum(1 for r in results for k in (r.get("checks") or {})
                    if k.startswith("env_"))
    env_fail = [(r["id"], k) for r in results
                for k, v in (r.get("checks") or {}).items()
                if k.startswith("env_") and v is not True]
    print("环境自检：%d 例，共 %d 项检查，未通过 %d 项"
          % (total, env_total, len(env_fail)))
    for cid, key in env_fail:
        print("  - %s: %s" % (cid, key))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="acadkit 真机验收")
    ap.add_argument("--only", default=None, help="族或 id，逗号分隔")
    ap.add_argument("--keep", action="store_true", help="跑完不退出 AutoCAD")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--case-timeout", type=float, default=120.0,
                    help="单例上限（秒），超时强杀 acad 并中止")
    args = ap.parse_args(argv)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    workdir = args.workdir or os.path.join(ROOT, "_scratch", "judges_%s" % stamp)
    os.makedirs(workdir, exist_ok=True)

    only = [k.strip() for k in args.only.split(",")] if args.only else None
    cases = caps.cases(only)
    if not cases:
        print("没有匹配的能力")
        return 2

    sig_before = env_signature()
    print("跑前环境指纹：%s" % sig_before)
    start_watchdog(args.case_timeout, workdir)

    info = launch.launch()
    app = info["app"]
    launched = info["launched"]
    print("AutoCAD：%s（profile=%r，等待 %ss）"
          % ("本次启动" if launched else "附加到已运行实例",
             info.get("profile"), info.get("waited_s")))

    rc = 0
    results: List[Dict[str, Any]] = []
    runner = None
    baseline = None
    try:
        runner = CaseRunner(app, workdir, log=lambda m: print(m))
        baseline = runner.ensure_baseline_doc()
        app = com.refresh(app)
        profile = launch.read_profile(app)
        print("活动文档 profile：%r" % (profile,))
        if profile is None or profile.strip() != env.REQUIRED_PROFILE:
            print("拒绝在非 %s 配置下跑用例（实际 %r）"
                  % (env.REQUIRED_PROFILE, profile))
            return 4
        for case in cases:
            print("\n>>> %s  %s" % (case.id, case.title))
            _WATCH.update(deadline=time.time() + args.case_timeout, case=case.id)
            res = runner.run(case)
            _WATCH["deadline"] = 0.0
            results.append(res)
            failed = [k for k, v in res["checks"].items() if v is False]
            print("    %s  %.1fs  %s"
                  % (MARK[bool(res["ok"])], res["duration_s"],
                     ("失败项：" + ", ".join(failed)) if failed else ""))
            for note in res.get("notes") or []:
                print("    note: %s" % note)
    except Exception as exc:                            # noqa: BLE001
        print("!! 跑用例时异常退出：%s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        rc = 1
    finally:
        try:
            if runner is not None and baseline is not None:
                fin = finish(app, baseline, quit_app=(launched and not args.keep))
                print("\n收尾：%s" % json.dumps(fin, ensure_ascii=False, default=str))
        except Exception as exc:                        # noqa: BLE001
            print("!! 收尾失败：%s: %s" % (type(exc).__name__, exc))
            rc = 1

    sig_after = env_signature()
    print("跑后环境指纹：%s" % sig_after)

    payload = {
        "tool": "acadkit live judges",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workdir": workdir,
        "autocad": {"launched": launched, "exe": info.get("exe"),
                    "profile": info.get("profile"),
                    "waited_s": info.get("waited_s")},
        "env_before": sig_before,
        "env_after": sig_after,
        "results": results,
    }
    out = os.path.join(workdir, "results.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("\n证据：%s" % out)

    print_table(results)

    env_bad = []
    if sig_after["sv_count"] > sig_before["sv_count"]:
        env_bad.append(".sv$ 增加了 %d 个" % (sig_after["sv_count"]
                                              - sig_before["sv_count"]))
    if launched and not args.keep and sig_after["process_count"] != 0:
        env_bad.append("AutoCAD 没退出（进程 %d）" % sig_after["process_count"])
    if env_bad:
        print("环境收尾不合格：%s" % "; ".join(env_bad))
        rc = rc or 1
    if results and not all(r["ok"] for r in results):
        rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
