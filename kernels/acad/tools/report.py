#!/usr/bin/env python3
"""一次求解 → 全套产物 + 一份报告。

    python tools/report.py --case brep-cantilever --part plate \
        --length 200 --width 100 --thickness 8 --force 100 \
        --title 支架校核 --number NSA-100 --outdir out

产出（都在 --outdir 下）：
    deformed.png    变形云图（FEA 结果）
    drawing.pdf     三视图 + 图框 + 标题栏（有 brep 零件时）
    part.step/stl   给 viewer 用的几何
    report.md       结论 + 判据 + 参数 + 产物清单
    report.json     同样内容的机器可读版

判据（全部写进 report.json 的 checks）：
    physics_ok  与解析解对账通过（沿用 fea_screen 的容差）
    png_ok      云图非空白（像素标准差）
    drawing_ok  PDF 幅面/文字复核通过
    viewer_ok   viewer 后端认了这些文件（STEP 被 step-source-status 接受）

退出码：0 = 物理判据 + 所有已请求的产物都过；1 = 有任一不过；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ACAD = os.path.dirname(HERE)                       # kernels/acad
ROOT = os.path.dirname(os.path.dirname(ACAD))      # 仓库根
sys.path.insert(0, os.path.join(ACAD, "src"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fea_screen as FS                            # noqa: E402
from acadkit.brep import drawing as DRW            # noqa: E402
from acadkit.brep import parts as B                # noqa: E402
from acadkit.brep.parts import BrepError           # noqa: E402
from acadkit.fea import view as VW                 # noqa: E402
from acadkit.fea.mesh import FeaError              # noqa: E402


def _resolve_tol(args) -> None:
    d = dict(FS.TOL_DEFAULTS)
    if args.case in ("bar", "cylinder") and abs(args.nu) > 1e-12 and d[args.case] < 1e-2:
        d[args.case] = 5e-2
    if args.tol <= 0:
        args.tol = d.get(args.case, 5e-2)


def _part_for(args):
    """按工况重建零件（只有 brep 类工况才有实体件）。"""
    case = args.case
    if case in ("brep-axial", "brep-cantilever", "combined", "render"):
        return FS._make_part(args)
    if case == "stepped":
        raw = [x.strip() for x in args.segments.split(",") if x.strip()]
        if not raw:
            raise BrepError("stepped 需要 --segments，如 20x60,12x40")
        segs = []
        for tok in raw:
            d_s, L_s = tok.lower().split("x")
            segs.append((float(d_s), float(L_s)))
        return B.stepped_shaft(segs)
    if case == "bracket":
        return B.bracket(length=args.length, root_height=args.root_h,
                         tip_height=args.tip_h, width=args.width)
    return None


def _fmt(v, digits: int = 6) -> str:
    try:
        return ("%%.%dg" % digits) % float(v)
    except (TypeError, ValueError):
        return str(v)


def _write_report(payload: dict, outdir: str) -> str:
    p = payload["params"]
    r = payload["result"]
    c = payload["checks"]
    L = []
    L.append("# 校核报告：%s" % payload["title"])
    L.append("")
    L.append("- 图号：%s" % (payload["number"] or "（未填）"))
    L.append("- 材料：%s" % (payload["material"] or "（未填）"))
    L.append("- 生成时间：%s" % payload["generated_at"])
    L.append("- 结论：**%s**" % ("通过" if all(c.values()) else "未通过"))
    L.append("")
    L.append("## 1 工况与参数")
    L.append("")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    for key in ("case", "part", "length", "width", "thickness", "diameter",
                "force", "torque", "pressure", "E", "nu", "mesh_size", "tol",
                "segments"):
        if key in p and p[key] not in ("", None, 0, 0.0):
            L.append("| %s | %s |" % (key, p[key]))
    L.append("")
    L.append("## 2 判据（与参考解对账）")
    L.append("")
    if r.get("stage") == "done":
        L.append("| 项 | 值 |")
        L.append("|---|---|")
        L.append("| 实测 | %s |" % _fmt(abs(r.get("measured", 0))))
        L.append("| 参考 | %s |" % _fmt(abs(r.get("expected", 0))))
        L.append("| 相对误差 | %s |" % _fmt(r.get("relative_error", 0), 4))
        L.append("| 容差 | %s |" % _fmt(r.get("tol", 0), 3))
        L.append("| 物理判据 | %s |" % ("通过" if r.get("ok") else "未通过"))
        if r.get("stress_nominal"):
            L.append("| 名义应力 | %s MPa |" % _fmt(r["stress_nominal"], 4))
    else:
        L.append("求解未完成：%s" % r.get("run", {}).get("stdout_tail", [])[-3:])
    L.append("")
    L.append("## 3 网格")
    L.append("")
    m = r.get("mesh") or {}
    if m:
        L.append("| 节点 | 单元 | 阶数 | 倒置单元 | 体积 mm³ |")
        L.append("|---|---|---|---|---|")
        L.append("| %s | %s | %s | %s | %s |"
                 % (m.get("nodes"), m.get("tets"), m.get("order"),
                    m.get("inverted"), _fmt(m.get("volume"), 8)))
    if r.get("part"):
        pa = r["part"]
        L.append("")
        L.append("网格体积 / 零件体积：%s / %s mm³（差 %.3f%%）"
                 % (_fmt(pa.get("mesh_volume")), _fmt(pa.get("part_volume")),
                    (pa.get("volume_error") or 0) * 100))
    L.append("")
    L.append("## 4 产物")
    L.append("")
    for k, v in (payload.get("artifacts") or {}).items():
        L.append("- %s：`%s`" % (k, v))
    if payload.get("viewer_url"):
        L.append("- 交互查看：%s" % payload["viewer_url"])
    L.append("")
    L.append("## 5 判据汇总")
    L.append("")
    for k, v in payload["checks"].items():
        L.append("- %s：%s" % (k, "通过" if v else "**未通过**"))
    L.append("")
    L.append("## 6 边界与假设")
    L.append("")
    L.append("- 这是**screening**，不是正式计算书；只覆盖线性静力。")
    L.append("- 默认二阶四面体 C3D10；与闭式解/积分参考解对账，误差与容差都写在上面。")
    L.append("- 名义应力按一维杆/梁公式给出，未含应力集中（孔边/端部）。")
    L.append("- 未覆盖：接触、塑性、屈曲、模态、疲劳。")
    path = os.path.join(outdir, "report.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def main(argv=None) -> int:
    ap = FS.build_parser()
    ap.add_argument("--outdir", default="", help="产物目录（默认建临时目录）")
    ap.add_argument("--title", default="", help="报告标题 / 图名")
    ap.add_argument("--number", default="", help="图号")
    ap.add_argument("--material", default="", help="材料")
    ap.add_argument("--sheet", default="A3", choices=tuple(DRW.SHEETS))
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-drawing", action="store_true")
    ap.add_argument("--no-viewer", action="store_true")
    args = ap.parse_args(argv)

    if args.case in ("sweep", "flange", "render"):
        print("report 不支持 %s（用 fea_screen / drawing 各自跑）" % args.case,
              file=sys.stderr)
        return 2
    _resolve_tol(args)

    outdir = os.path.abspath(args.outdir or os.path.join(
        os.environ.get("TEMP", "/tmp"),
        "nsa_report_%s_%d" % (args.case, int(time.time()))))
    os.makedirs(outdir, exist_ok=True)

    try:
        out = FS.run_case(args)
    except (FeaError, BrepError) as exc:
        print("求解失败：%s" % exc, file=sys.stderr)
        return 2
    if out.get("stage") != "done":
        print("未解出：%s" % (out.get("run") or {}).get("stdout_tail", [])[-4:],
              file=sys.stderr)
        return 1

    artifacts = {}
    checks = {"physics_ok": bool(out.get("ok"))}

    # 云图
    if not args.no_png:
        try:
            st = VW.deformed_from_result(out, os.path.join(outdir, "deformed.png"))
            artifacts["变形云图"] = st["path"]
            checks["png_ok"] = st["pixel_std"] > 2.0 and st["bytes"] > 2000
        except FeaError as exc:
            checks["png_ok"] = False
            artifacts["云图失败"] = str(exc)

    # 零件相关产物
    part = None
    try:
        part = _part_for(args)
    except (BrepError, ValueError) as exc:
        print("重建零件失败：%s" % exc, file=sys.stderr)
        return 2
    if part is not None:
        step = os.path.join(outdir, "part.step")
        stl = os.path.join(outdir, "part.stl")
        try:
            B.to_step(part, step)
            B.to_stl(part, stl)
            artifacts["STEP"] = step
            artifacts["STL"] = stl
        except BrepError:
            pass
        if not args.no_drawing:
            try:
                d = DRW.sheet_pdf(
                    part, os.path.join(outdir, "drawing.pdf"), sheet=args.sheet,
                    title_block={"title": args.title or args.case,
                                 "number": args.number, "material": args.material,
                                 "scale": ""})
                artifacts["图纸"] = d["path"]
                checks["drawing_ok"] = bool(d.get("page_size_ok")) and bool(
                    d.get("text_ok")) and d.get("pages") == 1
            except BrepError as exc:
                checks["drawing_ok"] = False
                artifacts["图纸失败"] = str(exc)
        if not args.no_viewer:
            try:
                import viewer as VIEWER
                v = VIEWER.start(outdir, wait=30)
                files = [os.path.basename(p) for p in (step, stl)
                         if os.path.isfile(p)]
                ver = VIEWER.verify(v["base"], outdir, files)
                artifacts["viewer"] = v["base"]
                payload_url = VIEWER.review_url(v["base"], outdir,
                                                os.path.basename(step)
                                                if os.path.isfile(step) else None)
                checks["viewer_ok"] = bool(ver.get("ok"))
            except Exception as exc:                  # noqa: BLE001
                checks["viewer_ok"] = False
                artifacts["viewer失败"] = str(exc)
                payload_url = ""

    payload = {
        "title": args.title or args.case,
        "number": args.number, "material": args.material,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "outdir": outdir,
        "params": {k: v for k, v in vars(args).items()
                   if k in ("case", "part", "length", "width", "thickness",
                            "diameter", "force", "torque", "pressure", "E", "nu",
                            "mesh_size", "tol", "segments")},
        "result": {k: out.get(k) for k in
                   ("stage", "ok", "measured", "expected", "relative_error",
                    "tol", "stress_nominal", "mesh", "part")},
        "artifacts": artifacts,
        "checks": checks,
        "viewer_url": locals().get("payload_url", ""),
    }
    md = _write_report(payload, outdir)
    js = os.path.join(outdir, "report.json")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)

    print("报告   ：%s" % md)
    print("机器读 ：%s" % js)
    print("判据   ：%s" % ", ".join("%s=%s" % (k, "过" if v else "未过")
                                   for k, v in checks.items()))
    for k, v in artifacts.items():
        print("产物   ：%s → %s" % (k, v))
    ok = all(checks.values())
    print("结论   ：%s" % ("通过" if ok else "未通过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
