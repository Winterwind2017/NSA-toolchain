r"""端到端示例：只用 **verified** 工具，从建模到出图导出，全流程一条命令跑完。

流程（每一步都有可验证的几何证据，不看返回值）：

1. 零件 A —— 底板 80×50×10，中心 Ø10 通孔，四角 R5 圆角
2. 零件 B —— 销轴 Ø10×20（旋转）
3. 装配 A+B —— 分开 130 mm 时干涉应为 0
4. 工程图 —— A 的前视图 + 注释，导出 PDF
5. 导出 —— A 的 STEP 与 IGES（判据是**文件头签名**，不是"调用没报错"）
6. 参数 —— 给 A 写一条全局变量方程（判据：计数 +1 且读回一致）

运行：

    python examples/e2e_demo.py
    python examples/e2e_demo.py --out D:/tmp/demo     # 指定输出目录

退出码：0 = 全部通过；4 = 有步骤未通过；2 = 环境问题（SolidWorks 没开/没装）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)


def _short(res: dict, keys: tuple) -> dict:
    return {k: v for k, v in (res.get("detail") or {}).items()
            if k in keys}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), ".swkit", "demo"))
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    try:
        from swkit.core.com import pyw
        app = pyw().Dispatch("SldWorks.Application")
    except Exception as exc:                        # noqa: BLE001
        print("连不上 SolidWorks：%s" % exc)
        return 2

    from swkit.verified import doc_ops as DO
    from swkit.verified import drawing as DW
    from swkit.verified import drawing_extra as DX
    from swkit.verified import features as F
    from swkit.verified import inspect as IN
    from swkit.verified import io_export as IO
    from swkit.verified import sketch_ops as S
    from swkit.verified import asm_ops as AO
    from swkit.verified import asm_state as AS

    steps = []

    def record(name: str, res: dict, keep: tuple = ()) -> bool:
        ok = bool(res.get("ok"))
        steps.append({"step": name, "ok": ok,
                      "checks": res.get("checks") or {},
                      "detail": _short(res, keep)})
        print("%-26s %s  %s" % (name, "PASS" if ok else "FAIL",
                                json.dumps(res.get("checks") or {}, ensure_ascii=False)))
        err = (res.get("detail") or {}).get("error")
        if err:
            print("%-26s       %s" % ("", str(err)[:110]))
        return ok

    t0 = time.time()

    # ── 1) 零件 A：底板 + 通孔 + 圆角 ────────────────────────────────
    app.CloseAllDocuments(True)
    plate = F.new_part()
    S.create_sketch(plate, "前视基准面")
    S.rectangle(plate, 0, 0, 80, 50)
    record("A.底板拉伸", F.extrude(plate, 10.0), ("volume_after_mm3",))

    # 通孔：必须在**顶面**上开草图，再切；且要选中草图（见 cut_check 的配方）
    plate = pyw().Dispatch(app.ActiveDoc)
    plate.ClearSelection2(True)
    from swkit.core.com import none_dispatch, val
    picked = plate.Extension.SelectByID2("", "FACE", 0.040, 0.025, 0.010,
                                         False, 0, none_dispatch(), 0)
    hole = {"ok": False, "checks": {"face_selected": bool(picked)},
            "detail": {}}
    if picked:
        plate.SketchManager.InsertSketch(True)
        S.circle(plate, 40.0, 25.0, 5.0)
        plate.SketchManager.InsertSketch(True)
        names = [str(val(f, "Name")) for f in F.iter_features(plate)]
        plate.ClearSelection2(True)
        plate.Extension.SelectByID2(names[-1], "SKETCH", 0, 0, 0, False, 0,
                                    none_dispatch(), 0)
        from swkit.verified import cuts as C
        hole = C.cut_extrude(plate, 10.0, through_all=True)
    record("A.中心通孔", hole, ("volume_before_mm3", "volume_after_mm3",
                               "volume_delta_mm3", "error"))

    plate = pyw().Dispatch(app.ActiveDoc)
    record("A.四角圆角R5", F.fillet(plate, 5.0, 4), ("volume_before_mm3", "volume_after_mm3"))

    plate = pyw().Dispatch(app.ActiveDoc)
    plate_path = os.path.join(out, "plate.SLDPRT")
    IO._saveas4(plate, plate_path, 0, 1)
    mass = IN.mass_properties(pyw().Dispatch(app.ActiveDoc))
    steps.append({"step": "A.保存", "ok": os.path.exists(plate_path),
                  "checks": {"file_exists": os.path.exists(plate_path)},
                  "detail": {"path": plate_path,
                             "volume_mm3": (mass.get("detail") or {}).get("volume_m3")}})
    print("%-26s %s" % ("A.保存", "PASS" if os.path.exists(plate_path) else "FAIL"))

    # ── 2) 零件 B：销轴（旋转）───────────────────────────────────────
    app.CloseAllDocuments(True)
    pin = F.new_part()
    S.create_sketch(pin, "前视基准面")
    S.centerline(pin, 0, 0, 0, 20)
    S.rectangle(pin, 0, 0, 5, 20)
    record("B.销轴旋转", F.revolve(pin, 360.0), ("volume_mm3",))
    pin = pyw().Dispatch(app.ActiveDoc)
    pin_path = os.path.join(out, "pin.SLDPRT")
    IO._saveas4(pin, pin_path, 0, 1)
    steps.append({"step": "B.保存", "ok": os.path.exists(pin_path),
                  "checks": {"file_exists": os.path.exists(pin_path)},
                  "detail": {"path": pin_path}})
    print("%-26s %s" % ("B.保存", "PASS" if os.path.exists(pin_path) else "FAIL"))

    # ── 3) 装配：分开 130 mm，干涉应为 0 ─────────────────────────────
    res = AS.create_assembly()
    asm_ok = bool(res.get("ok"))
    print("%-26s %s" % ("C.新建装配", "PASS" if asm_ok else "FAIL"))
    steps.append({"step": "C.新建装配", "ok": asm_ok, "checks": res.get("checks") or {},
                  "detail": _short(res, ("error",))})
    if asm_ok:
        # 记住装配体引用：下面 OpenDoc 打开零件后 ActiveDoc 会变成零件
        asm = pyw().Dispatch(app.ActiveDoc)
        # `AddComponent5` 要求零件**已经打开**（否则静默返回 None）
        for p in (plate_path, pin_path):
            if app.OpenDoc(p, 1) is None:
                print("打不开：%s" % p)
        r1 = AS.insert_component(asm, plate_path, 0.0, 0.0, 0.0, fixed=True)
        r2 = AS.insert_component(asm, pin_path, 130.0, 0.0, 0.0)
        record("C.插入两个零件", {"ok": bool(r1.get("ok") and r2.get("ok")),
                                  "checks": {"first": bool(r1.get("ok")),
                                             "second": bool(r2.get("ok")),
                                             "components":
                                                 (r2.get("detail") or {}).get("components_after")},
                                  "detail": {"err1": (r1.get("detail") or {}).get("error"),
                                             "err2": (r2.get("detail") or {}).get("error")}},
               ())
        inter = AO.check_interference(asm)
        record("C.干涉检查(分开)", inter, ("count", "expected", "error"))

    # ── 4) 工程图：前视图 + 注释 + PDF ──────────────────────────────
    res = DW.new_drawing(plate_path)
    dw_ok = bool(res.get("ok"))
    record("D.新建工程图", res, ("views", "sheet", "error"))
    if dw_ok:
        ddoc = pyw().Dispatch(app.ActiveDoc)
        record("D.注释", DW.note(ddoc, "swkit demo", 0.05, 0.05), ("text", "error"))
        ddoc = pyw().Dispatch(app.ActiveDoc)
        pdf = os.path.join(out, "plate.pdf")
        record("D.导出PDF", DX.export_pdf(ddoc, pdf), ("path", "bytes", "head", "error"))

    # ── 5) 导出 STEP / IGES（判据是文件签名）────────────────────────
    app.CloseAllDocuments(True)
    step_file = os.path.join(out, "plate.step")
    iges_file = os.path.join(out, "plate.igs")
    if app.OpenDoc(plate_path, 1) is not None:
        pdoc = pyw().Dispatch(app.ActiveDoc)
        record("E.STEP", IO.export_step(step_file), ("path", "bytes", "head", "error"))
        record("E.IGES", IO.export_iges(iges_file, doc=pdoc),
               ("path", "bytes", "head", "error"))

        # ── 6) 参数：写一条全局变量方程 ─────────────────────────────
        record("F.全局变量方程", DO.add_equation(pdoc, '"DEMO_W" = 40'),
               ("expression", "count_before", "count_after", "readback", "error"))

    # ── 汇总 ────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    passed = sum(1 for s in steps if s["ok"])
    print("\n" + "=" * 72)
    print("合计 %d 步，通过 %d，失败 %d，耗时 %.1f s" % (
        len(steps), passed, len(steps) - passed, elapsed))
    print("输出目录：%s" % out)
    report = os.path.join(out, "demo_report.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump({"elapsed_s": round(elapsed, 1), "passed": passed,
                   "total": len(steps), "steps": steps}, fh,
                  ensure_ascii=False, indent=2, default=str)
    print("报告：%s" % report)
    return 0 if passed == len(steps) else 4


if __name__ == "__main__":
    raise SystemExit(main())
