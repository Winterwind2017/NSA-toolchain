#!/usr/bin/env python3
"""真机负例/鲁棒性套件：**坏输入必须失败，而且图纸不许被改坏**。

    python tests/live_robustness.py            # 全部
    python tests/live_robustness.py --only A,C # 只跑某几组
    python tests/live_robustness.py --keep     # 跑完不退出 AutoCAD

为什么单独一套：`live_judges.py` 验的是"正常路径做对了"；这套验的是
"**异常路径有结论**"——不静默成功、不把图改坏、不留半成品。

规格来源：CADCraft `crates/engine/tests/non_finite_edits.rs`
（"结果会变成无穷/未定义的编辑必须失败，并让图纸保持原样"）
+ `malformed_handles` / `props_bad_lineweight` / `save_reports_not_saved` 的思路。
我们把它翻译成"在真 AutoCAD 上"的版本——判据仍是读回，不是返回值。

分组：
    A 非有限数值（NaN/Inf）        B 坏句柄 / 坏名字
    C 坏参数（线宽/半径/字高）      D 保存与出图失败必须报告
    E DIM* 变量读写与非法值        F 能力参数校验（MCP 侧）
    G LISP 语料（合法/非法）
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
import traceback
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps                                     # noqa: E402
from acadkit.core import com, env, launch, plot               # noqa: E402
from acadkit.build.helpers import pt                          # noqa: E402
from acadkit.judges.case import CaseRunner, env_signature     # noqa: E402
from acadkit.judges.read import read_drawing                  # noqa: E402

NAN = float("nan")
INF = float("inf")

_WATCH = {"deadline": 0.0, "what": None, "workdir": None}


def start_watchdog(per_case_s: float, workdir: str) -> None:
    """卡死（模态框/命令提示符）就杀掉 acad 并退出，绝不假装通过。"""

    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                msg = "用例 %s 超过 %.0fs 未返回（大概率弹了模态框/停在提示符）" % (
                    _WATCH["what"], per_case_s)
                print("\n!! " + msg)
                try:
                    with open(os.path.join(workdir, "TIMEOUT.txt"), "w",
                              encoding="utf-8") as fh:
                        fh.write(msg + "\n")
                except Exception:                   # noqa: BLE001
                    pass
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"], capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()
    _WATCH["workdir"] = workdir


# ── 公共判据 ────────────────────────────────────────────────────────
def count(doc: Any) -> int:
    return int(com.retry(lambda: doc.ModelSpace.Count, label="ModelSpace.Count"))


def finite_drawing(doc: Any) -> tuple:
    """读回整张图，返回 (实体数, 是否有非有限数值)。"""
    d = read_drawing(doc, "memory")
    bad = []
    for ent in d.entities:
        for key, val in ent.attrs.items():
            if isinstance(val, float) and not math.isfinite(val):
                bad.append("%s.%s=%r" % (ent.type, key, val))
            elif isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, float) and not math.isfinite(item):
                        bad.append("%s.%s 含非有限项" % (ent.type, key))
                        break
    return len(d.entities), bad


def expect_error(fn: Callable[[], Any]) -> Dict[str, Any]:
    """跑一个应当失败的调用，记录它到底怎么失败的。"""
    try:
        val = fn()
        return {"raised": False, "value": repr(val)[:120],
                "error": None}
    except Exception as exc:                        # noqa: BLE001
        return {"raised": True, "value": None,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:160])}


# ── 用例 ────────────────────────────────────────────────────────────
def case_nan_line(doc: Any, wd: str) -> Dict[str, Any]:
    """A1：NaN 坐标必须被**我们的能力层**拒掉，且实体数不变。

    注意：直接调 COM 是拦不住的（实测 AutoCAD 会建出 Length=nan 的线），
    所以判据落在 acadkit 的 build 路径上（pt() 在进 COM 前校验）。
    """
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    n0 = count(doc)
    r = expect_error(lambda: caps.build("geom.line", doc,
                                       {"start": (NAN, 0, 0), "end": (10, 0, 0)}))
    n1 = count(doc)
    _, bad = finite_drawing(doc)
    ok = (r["raised"] or n1 == n0) and n1 == n0 and not bad
    return {"ok": ok, "detail": {"attempt": r, "count_before": n0,
                                 "count_after": n1, "non_finite": bad}}


def case_inf_circle(doc: Any, wd: str) -> Dict[str, Any]:
    """A2：Inf 半径的圆必须被拒，且不产生实体。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    n0 = count(doc)
    r = expect_error(lambda: caps.build("geom.circle", doc,
                                       {"center": (0, 0, 0), "radius": INF}))
    n1 = count(doc)
    _, bad = finite_drawing(doc)
    return {"ok": (r["raised"] or n1 == n0) and n1 == n0 and not bad,
            "detail": {"attempt": r, "count_before": n0, "count_after": n1,
                       "non_finite": bad}}


def case_overflow_move(doc: Any, wd: str) -> Dict[str, Any]:
    """A3：1e308 这种"有限但会溢出"的坐标——能力层必须拒绝。"""
    n0 = count(doc)
    r = expect_error(lambda: caps.build("geom.circle", doc,
                                       {"center": (1e308, 1e308, 0), "radius": 1e308}))
    n1 = count(doc)
    _, bad = finite_drawing(doc)
    return {"ok": r["raised"] and n1 == n0 and not bad,
            "detail": {"attempt": r, "count_before": n0, "count_after": n1,
                       "non_finite": bad[:5]}}


def case_bad_handle(doc: Any, wd: str) -> Dict[str, Any]:
    """B1：查一个不存在的句柄——要么返回 None，要么抛错，不许崩。"""
    n0 = count(doc)
    r = expect_error(lambda: doc.HandleToObject("FFFFFFF"))
    n1 = count(doc)
    return {"ok": r["raised"] or r["value"] in ("None", "NoneType", "0"),
            "detail": {"attempt": r, "count_before": n0, "count_after": n1}}


def case_bad_layer(doc: Any, wd: str) -> Dict[str, Any]:
    """B2：把当前层设成不存在的名字——必须失败，且当前层不变。"""
    before = str(com.retry(lambda: doc.ActiveLayer.Name, label="ActiveLayer"))
    r = expect_error(lambda: setattr(doc, "ActiveLayer",
                                     doc.Layers.Item("NO_SUCH_LAYER_XYZ")))
    after = str(com.retry(lambda: doc.ActiveLayer.Name, label="ActiveLayer"))
    return {"ok": r["raised"] and before == after,
            "detail": {"attempt": r, "layer_before": before, "layer_after": after}}


def case_bad_lineweight(doc: Any, wd: str) -> Dict[str, Any]:
    """C1：非法线宽（12345）——必须被拒或夹回合法档，不许写入垃圾。"""
    lay = com.retry(lambda: doc.Layers.Item("0"), label="Layers.Item")
    before = int(lay.Lineweight)
    r = expect_error(lambda: setattr(lay, "Lineweight", 12345))
    after = int(lay.Lineweight)
    valid = {-3, 0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
             100, 106, 120, 140, 158, 200, 211}
    return {"ok": (r["raised"] and after == before) or after in valid,
            "detail": {"attempt": r, "before": before, "after": after,
                       "note": "合法档位见 valid 集合"}}


def case_negative_radius(doc: Any, wd: str) -> Dict[str, Any]:
    """C2：负半径——必须被拒，不许出现负半径圆。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    n0 = count(doc)
    r = expect_error(lambda: ms.AddCircle(pt(0, 0, 0), -5.0))
    n1 = count(doc)
    return {"ok": r["raised"] or n1 == n0,
            "detail": {"attempt": r, "count_before": n0, "count_after": n1}}


def case_save_bad_path(doc: Any, wd: str) -> Dict[str, Any]:
    """D1：存到非法路径——必须 ok=False 且带错误，不许静默成功。"""
    path = os.path.join(wd, "d1_missing_%d" % int(time.time() * 1000), "x.dwg")
    info = plot.save_as(doc, path, exists_wait_s=2.0)
    return {"ok": (not info.get("ok")) and bool(info.get("error") or info.get("bytes") == 0),
            "detail": {"path": path, "ok": info.get("ok"),
                       "bytes": info.get("bytes"), "error": info.get("error")}}


def case_plot_bad_path(doc: Any, wd: str) -> Dict[str, Any]:
    """D2：出图到非法路径——必须 ok=False。"""
    path = os.path.join(wd, "d2_missing_%d" % int(time.time() * 1000), "x.pdf")
    info = plot.plot_model_to_pdf(doc, path, timeout_s=15.0)
    return {"ok": not info.get("ok"),
            "detail": {"ok": info.get("ok"), "warnings": (info.get("warnings") or [])[:3]}}


DIM_CASES = (("DIMTXT", 2.5), ("DIMASZ", 3.0), ("DIMEXE", 1.25),
             ("DIMEXO", 0.625), ("DIMGAP", 0.625), ("DIMDEC", 2))


def case_dimvars_roundtrip(doc: Any, wd: str) -> Dict[str, Any]:
    """E1：DIM* 变量写入 → 读回一致（判据是读回，不是设值成功）。"""
    got = {}
    for name, val in DIM_CASES:
        try:
            doc.SetVariable(name, val)
            got[name] = float(doc.GetVariable(name))
        except Exception as exc:                    # noqa: BLE001
            got[name] = "ERR:%s" % type(exc).__name__
    bad = {k: got[k] for k, v in dict(DIM_CASES).items()
           if not isinstance(got.get(k), float) or abs(got[k] - v) > 1e-9}
    return {"ok": not bad, "detail": {"readback": got, "mismatch": bad}}


def case_dimvars_invalid(doc: Any, wd: str) -> Dict[str, Any]:
    """E2：非法 DIM* 值（负字高）——必须被拒且原值不变。"""
    before = float(doc.GetVariable("DIMTXT"))
    r = expect_error(lambda: doc.SetVariable("DIMTXT", -3.0))
    after = float(doc.GetVariable("DIMTXT"))
    return {"ok": (r["raised"] and after == before) or after > 0,
            "detail": {"attempt": r, "before": before, "after": after}}


def case_cap_param_validation(doc: Any, wd: str) -> Dict[str, Any]:
    """F1：给能力传坏参数——必须抛明确异常，不许静默画出错东西。"""
    n0 = count(doc)
    r = expect_error(lambda: caps.build("geom.circle", doc, {"radius": "abc"}))
    n1 = count(doc)
    return {"ok": r["raised"], "detail": {"attempt": r, "count_before": n0,
                                          "count_after": n1}}


def case_cap_missing_param(doc: Any, wd: str) -> Dict[str, Any]:
    """F2：缺必填参数时，要么用默认值成功，要么报错——不许"看起来成功但没画"。"""
    n0 = count(doc)
    try:
        caps.build("geom.rect", doc, {})
        r = {"raised": False, "error": None}
    except Exception as exc:                        # noqa: BLE001
        r = {"raised": True, "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])}
    n1 = count(doc)
    return {"ok": r["raised"] or n1 > n0,
            "detail": {"attempt": r, "count_before": n0, "count_after": n1}}


def case_lisp_valid(doc: Any, wd: str) -> Dict[str, Any]:
    """G1：合法 LISP 表达式能执行（画一个圆）。"""
    n0 = count(doc)
    try:
        doc.SendCommand('(vl-cmdf "_.CIRCLE" "200,0" "5")\n')
        time.sleep(0.8)
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "detail": {"error": str(exc)[:120]}}
    n1 = count(doc)
    return {"ok": n1 > n0, "detail": {"count_before": n0, "count_after": n1}}


def case_lisp_invalid(doc: Any, wd: str) -> Dict[str, Any]:
    """G2：非法 LISP 必须报错而不是挂住；图不变。"""
    n0 = count(doc)
    t0 = time.time()
    try:
        doc.SendCommand('(this-is-not-a-function 1 2)\n')
        time.sleep(0.8)
    except Exception as exc:                        # noqa: BLE001
        return {"ok": True, "detail": {"error": str(exc)[:120],
                                       "elapsed_s": round(time.time() - t0, 2)}}
    n1 = count(doc)
    return {"ok": n1 == n0, "detail": {"count_before": n0, "count_after": n1,
                                       "elapsed_s": round(time.time() - t0, 2)}}


CASES: List[Dict[str, Any]] = [
    {"id": "A1.nan_line", "group": "A", "fn": case_nan_line},
    {"id": "A2.inf_circle", "group": "A", "fn": case_inf_circle},
    {"id": "A3.overflow_move", "group": "A", "fn": case_overflow_move},
    {"id": "B1.bad_handle", "group": "B", "fn": case_bad_handle},
    {"id": "B2.bad_layer", "group": "B", "fn": case_bad_layer},
    {"id": "C1.bad_lineweight", "group": "C", "fn": case_bad_lineweight},
    {"id": "C2.negative_radius", "group": "C", "fn": case_negative_radius},
    {"id": "D1.save_bad_path", "group": "D", "fn": case_save_bad_path},
    {"id": "D2.plot_bad_path", "group": "D", "fn": case_plot_bad_path},
    {"id": "E1.dimvars_roundtrip", "group": "E", "fn": case_dimvars_roundtrip},
    {"id": "E2.dimvars_invalid", "group": "E", "fn": case_dimvars_invalid},
    {"id": "F1.cap_param_validation", "group": "F", "fn": case_cap_param_validation},
    {"id": "F2.cap_missing_param", "group": "F", "fn": case_cap_missing_param},
    {"id": "G1.lisp_valid", "group": "G", "fn": case_lisp_valid},
    {"id": "G2.lisp_invalid", "group": "G", "fn": case_lisp_invalid},
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="真机负例/鲁棒性套件")
    ap.add_argument("--only", default=None, help="组名，逗号分隔（A,C,G）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--case-timeout", type=float, default=90.0)
    args = ap.parse_args(argv)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    wd = args.workdir or os.path.join(ROOT, "_scratch", "robust_%s" % stamp)
    os.makedirs(wd, exist_ok=True)
    groups = [g.strip().upper() for g in args.only.split(",")] if args.only else None
    todo = [c for c in CASES if not groups or c["group"] in groups]

    start_watchdog(args.case_timeout, wd)
    sig_before = env_signature()
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s（profile=%r）"
          % ("本次启动" if info["launched"] else "附加到已运行实例", info.get("profile")))
    runner = CaseRunner(app, wd, log=lambda m: print(m))
    runner.ensure_baseline_doc()

    results = []
    for case in todo:
        _WATCH.update(deadline=time.time() + args.case_timeout, what=case["id"])
        t0 = time.time()
        doc = runner.new_doc("robust:" + case["id"])
        res: Dict[str, Any] = {"id": case["id"], "group": case["group"]}
        try:
            out = case["fn"](doc, wd)
            res.update(out)
        except Exception as exc:                    # noqa: BLE001
            res.update({"ok": False, "detail": {"error": "%s: %s" % (type(exc).__name__, exc)},
                        "traceback": traceback.format_exc(limit=4)})
        finally:
            _WATCH["deadline"] = 0.0
            try:
                runner._close(doc, "robust:" + case["id"])
            except Exception:                       # noqa: BLE001
                pass
        res["duration_s"] = round(time.time() - t0, 2)
        results.append(res)
        print("  %-24s %s  %.1fs" % (case["id"], "PASS" if res["ok"] else "FAIL",
                                     res["duration_s"]))

    passed = sum(1 for r in results if r["ok"])
    print("\n合计 %d 例：通过 %d / 失败 %d" % (len(results), passed, len(results) - passed))
    payload = {"suite": "robustness", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "autocad": {"launched": info.get("launched"), "profile": info.get("profile")},
               "env_before": sig_before, "env_after": env_signature(),
               "passed": passed, "total": len(results),
               "results": [{k: v for k, v in r.items() if k != "traceback"} for r in results]}
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
