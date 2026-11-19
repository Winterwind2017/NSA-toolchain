#!/usr/bin/env python3
"""修剪/延伸/偏移的无头驱动规格（真机）。

    python tests/live_spec_modify.py
    python tests/live_spec_modify.py --only M1,M3 --keep

为什么这条最难、也最值得留记录：这些命令靠**点选**推进，无头驱动要么成功、
要么卡在提示符上（我们的看门狗会杀 acad 并把结论写成 TIMEOUT，不会假装通过）。

判据仍是读回：用 `geom2d.trim` 里的几何决策算出**期望端点**，再看 AutoCAD 做出来的是不是这个。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.build.helpers import dbl, pt                      # noqa: E402
from acadkit.core import com, launch                           # noqa: E402
from acadkit.geom2d.trim import cut_params, extend_segment     # noqa: E402
from acadkit.judges.case import CaseRunner                     # noqa: E402

_WATCH = {"deadline": 0.0, "what": ""}
CASE_TIMEOUT = 90.0


def watchdog() -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                print("\n!! 用例 %s 超过 %.0fs，强杀 acad（结论记 TIMEOUT）"
                      % (_WATCH["what"], CASE_TIMEOUT))
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"], capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()


def _prepare(doc: Any) -> None:
    """把交互相关的变量压成"不弹框、不捕捉、不回声"。"""
    for name, value in (("OSMODE", 0), ("CMDECHO", 0), ("HIGHLIGHT", 0),
                        ("PICKADD", 1), ("FILEDIA", 0), ("CMDDIA", 0),
                        ("TRIMEXTENDMODE", 1)):        # 1 = 快速模式（直接点要剪掉的那段）
        try:
            doc.SetVariable(name, value)
        except Exception:                            # noqa: BLE001
            pass


def _iter_ents(doc: Any):
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    n = int(com.retry(lambda: ms.Count, label="Count"))
    for i in range(n):
        yield com.retry(lambda i=i: ms.Item(i), label="Item(%d)" % i)


def _lines(doc: Any) -> List[Tuple[float, float, float, float]]:
    """直接问 COM 要线段端点（与判据无关，纯粹读几何）。"""
    out = []
    for e in _iter_ents(doc):
        if str(getattr(e, "ObjectName", "")) != "AcDbLine":
            continue
        s0 = tuple(e.StartPoint)
        s1 = tuple(e.EndPoint)
        out.append((s0[0], s0[1], s1[0], s1[1]))
    return out


def _polyline_areas(doc: Any) -> List[float]:
    out = []
    for e in _iter_ents(doc):
        if str(getattr(e, "ObjectName", "")) != "AcDbPolyline":
            continue
        coords = list(e.Coordinates)
        xs, ys = coords[0::2], coords[1::2]
        n = len(xs)
        if n < 3:
            continue
        a = 0.0
        for i in range(n):
            j = (i + 1) % n
            a += xs[i] * ys[j] - xs[j] * ys[i]
        out.append(abs(a) / 2.0)
    return out


def _send(doc: Any, text: str, settle: float = 0.8) -> None:
    com.retry(lambda: doc.SendCommand(text), label="SendCommand(%r)" % text[:24])
    time.sleep(settle)


# ── 用例 ────────────────────────────────────────────────────────────
def case_trim(doc: Any, wd: str) -> Dict[str, Any]:
    """M1：一条横线被竖线切开，用 TRIM 快速模式剪掉右边。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(100, 0, 0)), label="AddLine")
    com.retry(lambda: ms.AddLine(pt(40, -10, 0), pt(40, 10, 0)), label="AddLine")
    _prepare(doc)
    _send(doc, "_.TRIM\n60,0\n\n", settle=1.2)

    horizontals = [t for t in _lines(doc) if abs(t[1]) < 1e-6 and abs(t[3]) < 1e-6]
    # 期望：只剩 0..40 那一段（用几何决策算的期望切点在 x=40）
    expected_cut = cut_params((0, 0), (100, 0), [((40, -10), (40, 10))])[0] * 100
    got_max = max((max(t[0], t[2]) for t in horizontals), default=None)
    return {"ok": got_max is not None and abs(got_max - 40.0) < 0.5,
            "detail": {"horizontals": horizontals, "expected_max_x": 40.0,
                       "expected_cut_x": expected_cut, "got_max_x": got_max}}


def case_extend(doc: Any, wd: str) -> Dict[str, Any]:
    """M2：短横线延伸到竖边界。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(40, 0, 0)), label="AddLine")
    com.retry(lambda: ms.AddLine(pt(80, -10, 0), pt(80, 10, 0)), label="AddLine")
    _prepare(doc)
    _send(doc, "_.EXTEND\n30,0\n\n", settle=1.2)

    horizontals = [t for t in _lines(doc) if abs(t[1]) < 1e-6 and abs(t[3]) < 1e-6]
    expected = extend_segment((0.0, 0.0), (40.0, 0.0), [((80, -10), (80, 10))])
    expect_x = max(expected[0][0], expected[1][0])
    got = max((max(t[0], t[2]) for t in horizontals), default=None)
    return {"ok": got is not None and abs(got - expect_x) < 0.5,
            "detail": {"horizontals": horizontals, "expected_max_x": expect_x,
                       "got_max_x": got}}


def case_offset(doc: Any, wd: str) -> Dict[str, Any]:
    """M3：闭合多段线外扩 5（点选内侧点决定方向）。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 40, 0, 40])), label="AddLightWeightPolyline")
    pl.Closed = True
    _prepare(doc)
    # OFFSET: 距离 5 → 选对象（点在底边中点）→ 指定侧点（内部）→ 回车结束
    _send(doc, "_.OFFSET\n5\n20,0\n20,20\n\n", settle=1.5)

    areas = _polyline_areas(doc)
    counts = len(areas)
    # 期望：外扩 5 → 50×50=2500；内缩 5 → 30×30=900
    hit = [a for a in areas if abs(a - 2500) < 30 or abs(a - 900) < 30]
    return {"ok": counts >= 2 and bool(hit),
            "detail": {"polyline_count": counts, "areas": areas,
                       "expect": "2500（外扩）或 900（内缩）"}}


CASES = [
    {"id": "M1.trim", "fn": case_trim},
    {"id": "M2.extend", "fn": case_extend},
    {"id": "M3.offset", "fn": case_offset},
]


def run(workdir: str, only: Optional[List[str]], keep: bool) -> int:
    os.makedirs(workdir, exist_ok=True)
    watchdog()
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s" % ("本次启动" if info["launched"] else "附加到已运行实例"))
    runner = CaseRunner(app, workdir, log=lambda m: print(m))
    runner.ensure_baseline_doc()

    todo = [c for c in CASES if not only or c["id"].split(".")[0] in only]
    results = []
    for case in todo:
        _WATCH.update(deadline=time.time() + CASE_TIMEOUT, what=case["id"])
        t0 = time.time()
        doc = runner.new_doc("mod:" + case["id"])
        res: Dict[str, Any] = {"id": case["id"]}
        try:
            res.update(case["fn"](doc, workdir))
        except Exception as exc:                     # noqa: BLE001
            res.update({"ok": False, "detail": {"error": "%s: %s" % (type(exc).__name__, exc)}})
        finally:
            _WATCH["deadline"] = 0.0
            try:
                runner._close(doc, "mod:" + case["id"])
            except Exception:                        # noqa: BLE001
                pass
        res["duration_s"] = round(time.time() - t0, 2)
        results.append(res)
        print("  %-14s %s  %.1fs" % (case["id"], "PASS" if res["ok"] else "FAIL",
                                     res["duration_s"]))

    passed = sum(1 for r in results if r["ok"])
    print("\n合计 %d 例：通过 %d / 失败 %d" % (len(results), passed, len(results) - passed))
    payload = {"suite": "spec_modify", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "passed": passed, "total": len(results), "results": results}
    outp = os.path.join(workdir, "results.json")
    with open(outp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("证据：%s" % outp)

    try:
        runner._close(runner.baseline_doc, "baseline")
        if info["launched"] and not keep:
            from acadkit.judges.case import finish
            print("收尾：%s" % finish(app, None, quit_app=True))
    except Exception as exc:                         # noqa: BLE001
        print("收尾失败：%s" % exc)
    return 0 if passed == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="修剪/延伸/偏移无头驱动（真机）")
    ap.add_argument("--only", default=None, help="M1,M2,M3")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args(argv)
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    wd = args.workdir or os.path.join(ROOT, "_scratch",
                                      "modify_%s" % time.strftime("%Y%m%d_%H%M%S"))
    return run(wd, only, args.keep)


if __name__ == "__main__":
    sys.exit(main())
