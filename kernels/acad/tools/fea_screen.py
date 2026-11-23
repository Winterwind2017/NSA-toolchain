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
from acadkit.fea import brep_bridge as BB   # noqa: E402
from acadkit.fea import cases as C          # noqa: E402
from acadkit.fea import runner as R         # noqa: E402
from acadkit.fea.mesh import FeaError       # noqa: E402

CASES = ("bar", "cylinder", "cantilever", "torsion", "plate",
         "brep-axial", "brep-cantilever")
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
                "brep-axial": 3e-2, "brep-cantilever": 5e-2}
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
                "brep-axial": ("force",), "brep-cantilever": ("force",)}[args.case]
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
