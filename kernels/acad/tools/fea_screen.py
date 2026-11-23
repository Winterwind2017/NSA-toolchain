#!/usr/bin/env python3
"""FEA screening：五种标准工况，全部带闭式解判据。

    python tools/fea_screen.py --case bar    --length 100 --width 10 --height 10 --force 10000
    python tools/fea_screen.py --case cylinder --length 300 --diameter 20 --force 5000
    python tools/fea_screen.py --case cantilever --length 200 --width 20 --height 20 --force 100
    python tools/fea_screen.py --case torsion --length 300 --radius 10 --torque 50000
    python tools/fea_screen.py --case plate  --side 100 --thickness 4 --pressure 0.01

判据（都可复算）：
    bar / cylinder : uz = FL/(EA)
    cantilever     : δ  = PL³/(3EI)
    torsion        : θ  = TL/(GJ)
    plate          : w  = 0.00406·q·a⁴/D

默认二阶四面体（C3D10）。退出码：0 = 在容差内；1 = 超差或未解出；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from acadkit.brep import parts as B         # noqa: E402
from acadkit.dfm.rules import check_milling, check_print3d  # noqa: E402
from acadkit.fea import brep_bridge as BB   # noqa: E402
from acadkit.fea import combined as CB      # noqa: E402
from acadkit.fea import flange as FL        # noqa: E402
from acadkit.fea import sweep as SW         # noqa: E402
from acadkit.fea import cases as C          # noqa: E402
from acadkit.fea import runner as R         # noqa: E402
from acadkit.fea.mesh import FeaError       # noqa: E402

CASES = ("bar", "cylinder", "cantilever", "torsion", "plate",
         "brep-axial", "brep-cantilever", "stepped", "bracket",
         "sweep", "flange", "combined")
PARTS = ("shaft", "plate", "flange")


def _make_part(args):
    """按 --part 造零件（复用 acadkit.brep 的参数化件）。"""
    if args.part == "shaft":
        if args.diameter <= 0:
            raise FeaError("shaft 需要 --diameter")
        return B.shaft(diameter=args.diameter, length=args.length)
    if args.part == "plate":
        return B.plate(length=args.length, width=args.width, thickness=args.thickness)
    if args.part == "flange":
        return B.flange(outer_d=args.outer, bore_d=args.bore, thickness=args.thickness,
                        bolt_holes=[{"diameter": 10, "bcd": args.bore * 1.6, "count": 4}])
    raise FeaError("未知零件：%s（可用：%s）" % (args.part, ", ".join(PARTS)))


def _workdir(args, tag: str) -> str:
    return args.workdir or os.path.join(
        os.environ.get("TEMP", "/tmp"), "fea_%s_%s" % (args.case, tag))


def run_case(args) -> dict:
    if args.case == "bar":
        return R.solve_bar(length=args.length, width=args.width, height=args.height,
                           mesh_size=_mesh(args, max(args.width, args.height)),
                           E=args.E, nu=args.nu, total_force=args.force,
                           tol=args.tol, workdir=_workdir(args, "bar"))
    if args.case == "cylinder":
        return R.solve_cylinder(radius=args.diameter / 2.0, length=args.length,
                                mesh_size=_mesh(args, args.diameter),
                                E=args.E, nu=args.nu, total_force=args.force,
                                tol=args.tol, workdir=_workdir(args, "cyl"))
    if args.case == "cantilever":
        return C.cantilever_beam(length=args.length, width=args.width, height=args.height,
                                 mesh_size=_mesh(args, args.height), E=args.E, nu=args.nu,
                                 force=args.force, order=args.order, tol=args.tol,
                                 workdir=_workdir(args, "cant"))
    if args.case == "torsion":
        return C.shaft_torsion(radius=args.radius or args.diameter / 2.0, length=args.length,
                               mesh_size=_mesh(args, (args.radius or args.diameter / 2.0) * 2),
                               E=args.E, nu=args.nu, torque=args.torque,
                               order=args.order, tol=args.tol,
                               workdir=_workdir(args, "tors"))
    if args.case in ("brep-axial", "brep-cantilever"):
        part = _make_part(args)
        size = args.mesh_size or _part_characteristic(args)
        if args.case == "brep-axial":
            return BB.axial_part(part, force=args.force, E=args.E, nu=args.nu,
                                 mesh_size=size, order=args.order, tol=args.tol,
                                 workdir=_workdir(args, "pax"))
        return BB.cantilever_part(part, force=args.force, E=args.E, nu=args.nu,
                                  mesh_size=size, axis="x", load_axis="z",
                                  order=args.order, tol=args.tol,
                                  workdir=_workdir(args, "pcant"))
    if args.case == "plate":
        # 板默认 t/h=2（够 5% 判据，且比 t/h=3 便宜一个量级）
        return C.simply_supported_plate(side=args.side, thickness=args.thickness,
                                        mesh_size=_mesh(args, args.thickness * 1.5),
                                        E=args.E, nu=args.nu, pressure=args.pressure,
                                        order=args.order, tol=args.tol,
                                        workdir=_workdir(args, "plate"))
    raise FeaError("未知工况：%s（可用：%s）" % (args.case, ", ".join(CASES)))


def _part_characteristic(args) -> float:
    """**最终**网格尺寸（不经 _mesh 再除 3）。"""
    if args.part == "shaft":
        return args.diameter / 4.0
    if args.part == "flange":
        return args.thickness / 4.0
    return args.thickness / 2.0        # 板：t/h=2 够判据，再细会跑到百万自由度


def _mesh(args, characteristic: float) -> float:
    return args.mesh_size or max(characteristic / 3.0, 0.5)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FEA screening（五种工况，带解析判据）")
    ap.add_argument("--case", default="bar", choices=CASES)
    ap.add_argument("--length", type=float, default=100.0)
    ap.add_argument("--width", type=float, default=10.0)
    ap.add_argument("--height", type=float, default=10.0)
    ap.add_argument("--diameter", type=float, default=0.0)
    ap.add_argument("--radius", type=float, default=0.0)
    ap.add_argument("--side", type=float, default=100.0, help="板边长")
    ap.add_argument("--part", default="shaft", choices=PARTS, help="brep 零件类型")
    ap.add_argument("--outer", type=float, default=120.0, help="法兰外径")
    ap.add_argument("--bore", type=float, default=40.0, help="法兰内孔")
    ap.add_argument("--sweep-param", default="thickness", choices=("thickness", "diameter"))
    ap.add_argument("--sweep-values", default="", help="逗号分隔，如 8,12,16")
    ap.add_argument("--max-deflection", type=float, default=0.0, help="许用挠度 mm")
    ap.add_argument("--max-stress", type=float, default=0.0, help="许用应力 MPa")
    ap.add_argument("--csv", default="", help="扫描结果写 CSV 的路径")
    ap.add_argument("--bolt-count", type=int, default=8)
    ap.add_argument("--bolt-d", type=float, default=12.0)
    ap.add_argument("--bcd", type=float, default=0.0, help="螺栓分布圆直径（0=按 bore*1.6）")
    ap.add_argument("--preload", type=float, default=0.0, help="单螺栓预紧力 N")
    ap.add_argument("--sigma-allow", type=float, default=140.0, help="许用应力 MPa")
    ap.add_argument("--process", default="print3d", choices=("print3d", "milling"),
                    help="combined 用法里的制造工艺")
    ap.add_argument("--nozzle", type=float, default=0.4, help="3D 打印喷嘴 mm")
    ap.add_argument("--concentration", type=float, default=3.0,
                    help="名义→峰值应力集中系数")
    ap.add_argument("--segments", default="", help='阶梯轴段，如 "20x60,12x40,16x100"（直径x长度）')
    ap.add_argument("--root-h", type=float, default=30.0, help="支架根部高")
    ap.add_argument("--tip-h", type=float, default=10.0, help="支架端部高")
    ap.add_argument("--thickness", type=float, default=4.0, help="板厚")
    ap.add_argument("--force", type=float, default=0.0, help="轴向/悬臂载荷 N")
    ap.add_argument("--torque", type=float, default=0.0, help="扭矩 N·mm")
    ap.add_argument("--pressure", type=float, default=0.0, help="板面压力 MPa")
    ap.add_argument("--E", type=float, default=210000.0)
    ap.add_argument("--nu", type=float, default=0.3)
    ap.add_argument("--mesh-size", type=float, default=0.0)
    ap.add_argument("--order", type=int, default=2, choices=(1, 2))
    ap.add_argument("--tol", type=float, default=0.0, help="覆盖默认容差")
    ap.add_argument("--workdir", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    # 每种工况的必备参数与默认容差
    defaults = {"bar": 1e-6, "cylinder": 5e-3, "cantilever": 1e-2,
                "torsion": 1e-2, "plate": 5e-2,
                "brep-axial": 3e-2, "brep-cantilever": 5e-2,
                "sweep": 5e-2, "flange": 1.0, "combined": 5e-2,
                "stepped": 6e-2, "bracket": 3e-2}
    note = ""
    if args.case in ("bar", "cylinder") and abs(args.nu) > 1e-12 and defaults[args.case] < 1e-2:
        # 一维杆理论假设横向自由收缩；固定端会限制泊松收缩（ν≠0 时偏刚 ~0.5%）
        defaults[args.case] = 5e-2
        note = ("提示：ν=%.2f≠0 时固定端限制泊松收缩，与一维杆理论本就有偏差，"
                "容差自动放宽到 5e-2；要严格对账请加 --nu 0" % args.nu)
    if args.tol <= 0:
        args.tol = defaults[args.case]
    required = {"bar": ("force",), "cylinder": ("force",), "cantilever": ("force",),
                "torsion": ("torque",), "plate": ("pressure",),
                "brep-axial": ("force",), "brep-cantilever": ("force",),
                "sweep": ("force",), "flange": (), "combined": ("force",),
                "stepped": ("force",), "bracket": ("force",)}[args.case]
    missing = [n for n in required if getattr(args, n) <= 0]
    if missing:
        print("参数错误：%s 工况需要 --%s > 0" % (args.case, ", --".join(missing)),
              file=sys.stderr)
        return 2
    if args.case == "cylinder" and args.diameter <= 0:
        print("参数错误：cylinder 需要 --diameter", file=sys.stderr)
        return 2
    if args.case == "torsion" and args.radius <= 0 and args.diameter <= 0:
        print("参数错误：torsion 需要 --radius 或 --diameter", file=sys.stderr)
        return 2

    # 阶梯轴 / 变截面支架（真实件）
    if args.case in ("stepped", "bracket"):
        try:
            if args.case == "stepped":
                raw = [x.strip() for x in args.segments.split(",") if x.strip()]
                if not raw:
                    print("参数错误：stepped 需要 --segments", file=sys.stderr)
                    return 2
                segs = []
                for tok in raw:
                    d_s, L_s = tok.lower().split("x")
                    segs.append((float(d_s), float(L_s)))
                part = B.stepped_shaft(segs)
                min_d = min(d for d, _L in segs)
                size = args.mesh_size or min_d / 4.0
                out = BB.stepped_axial(part, segments=segs, force=args.force,
                                       E=args.E, nu=args.nu, mesh_size=size,
                                       order=args.order, tol=args.tol,
                                       workdir=_workdir(args, "stp"))
            else:
                part = B.bracket(length=args.length, root_height=args.root_h,
                                 tip_height=args.tip_h, width=args.width)
                size = args.mesh_size or args.tip_h / 2.0
                out = BB.bracket_cantilever(part, length=args.length,
                                            root_height=args.root_h,
                                            tip_height=args.tip_h, width=args.width,
                                            force=args.force, E=args.E, nu=args.nu,
                                            mesh_size=size, order=args.order,
                                            tol=args.tol, workdir=_workdir(args, "brk"))
        except (FeaError, ValueError) as exc:
            print("FEA 失败：%s" % exc, file=sys.stderr)
            return 2
        if out.get("stage") != "done":
            print("未解出：%s" % (out.get("run") or {}).get("stdout_tail", [])[-4:])
            return 1
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            p = out["part"]
            print("工况：%s  体积=%.2f mm³，网格=%.2f mm³（差 %.3f%%）"
                  % (args.case, p["part_volume"], p["mesh_volume"], p["volume_error"] * 100))
            print("实测：%.7g" % abs(out["measured"]))
            print("参考：%.7g" % abs(out["expected"]))
            print("相对误差：%.3e（容差 %.1e）" % (out["relative_error"], args.tol))
            print("结论：%s" % ("ok" if out.get("ok") else "超差"))
        return 0 if out.get("ok") else 1

    # 参数扫描
    if args.case == "sweep":
        raw = [x.strip() for x in args.sweep_values.split(",") if x.strip()]
        if not raw:
            print("参数错误：sweep 需要 --sweep-values", file=sys.stderr)
            return 2
        values = [float(x) for x in raw]
        if args.part == "plate":
            factory = lambda v: B.plate(length=args.length, width=args.width, thickness=v)
            kwargs = {"axis": "x", "load_axis": "z"}
            mesh = args.mesh_size or min(values) / 2.0
        elif args.part == "shaft":
            factory = lambda v: B.shaft(diameter=v, length=args.length)
            kwargs = {}
            mesh = args.mesh_size or min(values) / 4.0
        else:
            print("参数错误：sweep 只支持 --part plate|shaft", file=sys.stderr)
            return 2
        case = "cantilever" if args.part == "plate" else "axial"
        try:
            sw = SW.sweep(factory=factory, param=args.sweep_param, values=values,
                          case=case, force=args.force, E=args.E, nu=args.nu,
                          mesh_size=mesh, order=args.order, tol=args.tol,
                          workdir=_workdir(args, "sweep"), kwargs=kwargs)
        except FeaError as exc:
            print("扫描失败：%s" % exc, file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"param": sw.param, "case": sw.case,
                              "points": [p.to_dict() for p in sw.points]},
                             ensure_ascii=False, indent=2))
        else:
            print(sw.to_text())
        if args.csv:
            print("CSV：%s" % sw.to_csv(args.csv))
        best = None
        if args.max_deflection > 0 or args.max_stress > 0:
            best = SW.pick_min(sw, max_deflection=args.max_deflection or None,
                               max_stress=args.max_stress or None)
            print("最小满足值：%s" % ("(无解)" if best is None else "%g mm" % best))
        return 0 if best is not None or (args.max_deflection <= 0 and args.max_stress <= 0) else 1

    # FEA + DFM 合成
    if args.case == "combined":
        part = _make_part(args)
        size = args.mesh_size or _part_characteristic(args)
        try:
            if args.part == "plate":
                fea = BB.cantilever_part(part, force=args.force, E=args.E, nu=args.nu,
                                         mesh_size=size, axis="x", load_axis="z",
                                         order=args.order, tol=args.tol,
                                         workdir=_workdir(args, "cmb"))
            else:
                fea = BB.axial_part(part, force=args.force, E=args.E, nu=args.nu,
                                    mesh_size=size, order=args.order, tol=args.tol,
                                    workdir=_workdir(args, "cmb"))
        except FeaError as exc:
            print("FEA 失败：%s" % exc, file=sys.stderr)
            return 2
        bbox = part.bbox()
        min_dim = min(bbox["xlen"], bbox["ylen"], bbox["zlen"])
        if args.process == "print3d":
            dfm = check_print3d(min_wall=min_dim, overhang_deg=0.0,
                                nozzle=args.nozzle)
            note = "DFM 只检查打印最小壁厚（= %.2f mm）与喷嘴匹配" % min_dim
        else:
            dfm = check_milling(tool_diameter=6.0, pockets=[])
            note = "DFM 只检查铣削刀具可达性（无型腔，恒通过）"
        try:
            res = CB.combine(fea, sigma_allow=args.sigma_allow, dfm=dfm,
                             deflection_limit=args.max_deflection or None,
                             concentration=args.concentration)
        except FeaError as exc:
            print("合成失败：%s" % exc, file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            print(note)
            print(res.to_text())
        return 0 if res.ok else 1

    # 法兰简化校核（不开 FEA）
    if args.case == "flange":
        try:
            rep = FL.flange_check(
                outer_d=args.outer, bore_d=args.bore, thickness=args.thickness,
                bolt_count=args.bolt_count, bolt_d=args.bolt_d,
                bcd=args.bcd or args.bore * 1.6,
                preload_per_bolt=args.preload or (args.force or 1.0),
                sigma_allow=args.sigma_allow)
        except ValueError as exc:
            print("参数错误：%s" % exc, file=sys.stderr)
            return 2
        print(rep.to_text())
        return 0 if rep.ok else 1

    try:
        out = run_case(args)
    except FeaError as exc:
        print("FEA 失败：%s" % exc, file=sys.stderr)
        return 2

    solved = out.get("stage") == "done"
    payload = {"case": args.case, "order": args.order, "tol": args.tol,
               "ok": bool(out.get("ok")), "stage": out.get("stage"),
               "measured": out.get("measured"), "expected": out.get("expected"),
               "relative_error": out.get("relative_error"),
               "mesh": out.get("mesh"), "run": out.get("run")}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        m = out.get("mesh") or {}
        if note:
            print(note)
        label = args.case if not args.case.startswith("brep") else "%s/%s" % (args.case, args.part)
        print("工况：%s（order=%d）" % (label, args.order))
        if out.get("part"):
            p = out["part"]
            print("零件：%s 体积=%.2f mm³，网格体积=%.2f mm³（差 %.3f%%）"
                  % (args.part, p["part_volume"], p["mesh_volume"], p["volume_error"] * 100))
        print("网格：%s 节点 / %s 单元 / 倒置 %s / 体积 %s mm³"
              % (m.get("nodes"), m.get("tets"), m.get("inverted"), m.get("volume")))
        if solved:
            print("实测：%.7g" % abs(out["measured"]))
            print("理论：%.7g" % abs(out["expected"]))
            print("相对误差：%.3e（容差 %.1e）"
                  % (out["relative_error"], args.tol))
            print("结论：%s" % ("ok" if out.get("ok") else "超差"))
        else:
            print("未解出：%s" % (out.get("run") or {}).get("stdout_tail", [])[-4:])
            print("结论：not_solved")

    if not solved:
        return 1
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
