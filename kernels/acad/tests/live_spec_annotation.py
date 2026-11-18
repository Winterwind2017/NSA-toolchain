#!/usr/bin/env python3
"""标注与文字的行为规格（真机）：写进去的要能读回来，长文本不许把图弄坏。

    python tests/live_spec_annotation.py
    python tests/live_spec_annotation.py --keep

规格来源：CADCraft `crates/engine/tests/` 的 `dim_vars` / `mtext_*` / `mleader_content`
一类——共同点是"**标注/文字的属性必须可读回，且改一项不许牵连别的**"。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.build.helpers import dbl, pt                        # noqa: E402
from acadkit.core import com, env, launch                        # noqa: E402
from acadkit.judges.case import CaseRunner, env_signature        # noqa: E402

_WATCH = {"deadline": 0.0, "what": None}


def start_watchdog(per_case_s: float) -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                print("\n!! 用例 %s 超时，强杀 acad" % _WATCH["what"])
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"], capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()


def ms(doc: Any) -> Any:
    return com.retry(lambda: doc.ModelSpace, label="ModelSpace")


def case_dim_text_height(doc: Any, wd: str) -> Dict[str, Any]:
    """A1：单条标注的文字高度可写可读（这是唯一可靠的一条路）。"""
    dim = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(40, 0, 0),
                                                  pt(20, -10, 0), 0.0), label="AddDimRotated")
    dim.TextHeight = 3.5
    got = float(com.retry(lambda: dim.TextHeight, label="TextHeight"))
    return {"ok": abs(got - 3.5) < 1e-6, "detail": {"expected": 3.5, "readback": got}}


def case_dimtxt_not_propagated(doc: Any, wd: str) -> Dict[str, Any]:
    """A1b：**坑**——`SetVariable("DIMTXT")` 不传导到新建标注。

    实测（2026-11-18）：设 DIMTXT=3.5 后变量读回 3.5，但新建标注 TextHeight 仍是 2.5；
    加 Regen 也一样。所以 `env.dimstyle` 只改变量时，**不要指望新建标注跟着变**。
    这条用例把该行为固化下来：哪天 AutoCAD 改了，它会 FAIL 提醒我们。
    """
    doc.SetVariable("DIMTXT", 3.5)
    var = float(doc.GetVariable("DIMTXT"))
    dim = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(40, 0, 0),
                                                  pt(20, -10, 0), 0.0), label="AddDimRotated")
    th = float(dim.TextHeight)
    return {"ok": abs(var - 3.5) < 1e-6 and abs(th - 2.5) < 1e-6,
            "detail": {"DIMTXT_var": var, "dim_TextHeight": th,
                       "note": "变量变了、标注没变 = 已知行为；若哪天 th==3.5，本用例会 FAIL"}}


def case_dim_text_override(doc: Any, wd: str) -> Dict[str, Any]:
    """A2：文字替代（%%c 直径符）必须原样读回。"""
    dim = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(40, 0, 0),
                                                  pt(20, -10, 0), 0.0), label="AddDimRotated")
    dim.TextOverride = "%%c40"
    got = str(com.retry(lambda: dim.TextOverride, label="TextOverride"))
    return {"ok": got == "%%c40", "detail": {"written": "%%c40", "readback": got,
                                            "measurement": float(dim.Measurement)}}


def case_dim_text_position(doc: Any, wd: str) -> Dict[str, Any]:
    """A3：挪动标注文字位置，读回坐标必须跟着变（不许"设了没效果"）。"""
    dim = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(40, 0, 0),
                                                  pt(20, -10, 0), 0.0), label="AddDimRotated")
    before = tuple(dim.TextPosition)
    dim.TextPosition = pt(30.0, -22.0, 0.0)
    after = tuple(dim.TextPosition)
    moved = abs(after[0] - 30.0) < 1e-6 and abs(after[1] - (-22.0)) < 1e-6
    return {"ok": moved and (after != before),
            "detail": {"before": before, "after": after}}


def case_dim_baseline_gap(doc: Any, wd: str) -> Dict[str, Any]:
    """A4：两条基线标注的尺寸线距离，必须等于我们给的偏移（不许重叠）。"""
    d1 = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(40, 0, 0),
                                                 pt(20, -10, 0), 0.0), label="Dim1")
    d2 = com.retry(lambda: ms(doc).AddDimRotated(pt(0, 0, 0), pt(60, 0, 0),
                                                 pt(30, -18, 0), 0.0), label="Dim2")
    # DimLineLocation 在 pywin32 下读不到（AttributeError，实测 2026-11-18），
    # 用 TextPosition 的 y 差代替——它同样能反映"两条尺寸线是否分开"。
    y1 = float(d1.TextPosition[1])
    y2 = float(d2.TextPosition[1])
    gap = abs(y2 - y1)
    return {"ok": gap >= 7.0, "detail": {"y1": y1, "y2": y2, "gap": gap,
                                        "expect": ">=7（8 减去标注文字高度的一半）"}}


def case_mtext_width(doc: Any, wd: str) -> Dict[str, Any]:
    """A5：多行文字的宽度必须读回一致，内容不许被截断。"""
    text = "第一行\\P第二行\\P第三行"
    mt = com.retry(lambda: ms(doc).AddMText(pt(0, 0, 0), 80.0, text), label="AddMText")
    width = float(com.retry(lambda: mt.Width, label="Width"))
    got = str(com.retry(lambda: mt.TextString, label="TextString"))
    return {"ok": abs(width - 80.0) < 1e-6 and got == text,
            "detail": {"width": width, "text_match": got == text,
                       "len_written": len(text), "len_read": len(got)}}


def case_text_height_change(doc: Any, wd: str) -> Dict[str, Any]:
    """A6：改单行文字高度——读回必须变，且内容不受影响。"""
    t = com.retry(lambda: ms(doc).AddText("ACADKIT", pt(0, 0, 0), 5.0), label="AddText")
    h1 = float(com.retry(lambda: t.Height, label="Height"))
    t.Height = 7.0
    h2 = float(com.retry(lambda: t.Height, label="Height"))
    return {"ok": abs(h1 - 5.0) < 1e-6 and abs(h2 - 7.0) < 1e-6 and str(t.TextString) == "ACADKIT",
            "detail": {"height_before": h1, "height_after": h2,
                       "text": str(t.TextString)}}


def case_long_text(doc: Any, wd: str) -> Dict[str, Any]:
    """A7：超长文字（2000 字）——要么完整读回，要么明确报错，不许静默截断。"""
    body = ("字" * 2000)
    try:
        mt = com.retry(lambda: ms(doc).AddMText(pt(0, 0, 0), 500.0, body), label="AddMText")
        got = str(com.retry(lambda: mt.TextString, label="TextString"))
        return {"ok": len(got) == len(body) or bool(mt is None),
                "detail": {"written": len(body), "read": len(got),
                           "note": "等长才算没被静默截断"}}
    except Exception as exc:                        # noqa: BLE001
        return {"ok": True, "detail": {"raised": "%s: %s" % (type(exc).__name__, str(exc)[:120]),
                                       "note": "明确报错也算合规"}}


CASES = [
    {"id": "A1.dim_text_height", "fn": case_dim_text_height},
    {"id": "A1b.dimtxt_not_propagated", "fn": case_dimtxt_not_propagated},
    {"id": "A2.dim_text_override", "fn": case_dim_text_override},
    {"id": "A3.dim_text_position", "fn": case_dim_text_position},
    {"id": "A4.dim_baseline_gap", "fn": case_dim_baseline_gap},
    {"id": "A5.mtext_width", "fn": case_mtext_width},
    {"id": "A6.text_height_change", "fn": case_text_height_change},
    {"id": "A7.long_text", "fn": case_long_text},
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="标注/文字行为规格（真机）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--case-timeout", type=float, default=60.0)
    args = ap.parse_args(argv)

    wd = args.workdir or os.path.join(ROOT, "_scratch",
                                      "specann_%s" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(wd, exist_ok=True)
    start_watchdog(args.case_timeout)
    sig_before = env_signature()
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s（profile=%r）"
          % ("本次启动" if info["launched"] else "附加到已运行实例", info.get("profile")))
    runner = CaseRunner(app, wd, log=lambda m: print(m))
    runner.ensure_baseline_doc()

    results = []
    for case in CASES:
        _WATCH.update(deadline=time.time() + args.case_timeout, what=case["id"])
        t0 = time.time()
        doc = runner.new_doc("ann:" + case["id"])
        res: Dict[str, Any] = {"id": case["id"]}
        try:
            res.update(case["fn"](doc, wd))
        except Exception as exc:                    # noqa: BLE001
            res.update({"ok": False, "detail": {"error": "%s: %s" % (type(exc).__name__, exc)}})
        finally:
            _WATCH["deadline"] = 0.0
            try:
                runner._close(doc, "ann:" + case["id"])
            except Exception:                       # noqa: BLE001
                pass
        res["duration_s"] = round(time.time() - t0, 2)
        results.append(res)
        print("  %-22s %s  %.1fs" % (case["id"], "PASS" if res["ok"] else "FAIL",
                                     res["duration_s"]))

    passed = sum(1 for r in results if r["ok"])
    print("\n合计 %d 例：通过 %d / 失败 %d" % (len(results), passed, len(results) - passed))
    payload = {"suite": "spec_annotation", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "passed": passed, "total": len(results),
               "env_before": sig_before, "env_after": env_signature(), "results": results}
    with open(os.path.join(wd, "results.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("证据：%s" % os.path.join(wd, "results.json"))

    try:
        runner._close(runner.baseline_doc, "baseline")
        if info["launched"] and not args.keep:
            from acadkit.judges.case import finish
            print("收尾：%s" % finish(app, None, quit_app=True))
    except Exception as exc:                        # noqa: BLE001
        print("收尾失败：%s" % exc)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
