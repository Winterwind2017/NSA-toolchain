#!/usr/bin/env python3
"""轴向拉伸 screening：划网格 → 写 inp → 调 ccx → 与解析解对账。

    python tools/fea_screen.py --length 100 --width 10 --height 10 --force 10000
    python tools/fea_screen.py --length 300 --diameter 20 --force 5000 --json

判据（不是"跑完就算成功"）：
  让 ν=0 时位移必须等于 FL/(EA)（相对误差 ≤1e-6）；
  ν≠0 时固定端限制横向收缩，位移会偏小 —— 这时只报数并标 poisson_constraint。

退出码：0 = 解出来且（ν=0 时）与理论一致；1 = 没解出来；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from acadkit.fea import runner as R          # noqa: E402
from acadkit.fea.mesh import FeaError        # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="轴向拉伸 FEA screening")
    ap.add_argument("--length", type=float, required=True, help="轴向长度 mm")
    ap.add_argument("--width", type=float, default=10.0, help="截面宽（矩形）mm")
    ap.add_argument("--height", type=float, default=10.0, help="截面高（矩形）mm")
    ap.add_argument("--diameter", type=float, default=0.0,
                    help="给直径则按圆截面算截面积（忽略 width/height 的面积）")
    ap.add_argument("--force", type=float, required=True, help="总拉力 N")
    ap.add_argument("--E", type=float, default=210000.0, help="弹性模量 MPa")
    ap.add_argument("--nu", type=float, default=0.0, help="泊松比（0 才能与一维理论严格对账）")
    ap.add_argument("--mesh-size", type=float, default=0.0, help="目标单元尺寸 mm，默认取截面/3")
    ap.add_argument("--workdir", default="", help="工作目录（默认建临时目录）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        area = (math.pi * (args.diameter / 2) ** 2 if args.diameter > 0
                else args.width * args.height)
        mesh_size = args.mesh_size or max(args.width, args.height) / 3.0
        workdir = args.workdir or os.path.join(
            os.environ.get("TEMP", "/tmp"), "fea_screen_%dx%g" % (int(args.length), args.force))
        if args.diameter > 0:
            out = R.solve_cylinder(radius=args.diameter / 2.0, length=args.length,
                                   mesh_size=mesh_size, E=args.E, nu=args.nu,
                                   total_force=args.force, workdir=workdir)
        else:
            out = R.solve_bar(length=args.length, width=args.width, height=args.height,
                              mesh_size=mesh_size, E=args.E, nu=args.nu,
                              total_force=args.force, workdir=workdir)
    except FeaError as exc:
        print("FEA 失败：%s" % exc, file=sys.stderr)
        return 2

    solved = out.get("stage") == "done"
    if not solved:
        verdict = "not_solved"
    elif out.get("ok"):
        verdict = "ok"
    elif args.nu != 0.0:
        verdict = "poisson_constraint"      # ν≠0 的约束效应，不是错
    else:
        verdict = "mismatch"

    payload = {"verdict": verdict, "area": round(area, 6), "mesh_size": mesh_size,
               **{k: out.get(k) for k in ("ok", "stage", "mesh", "inp", "run",
                                          "measured_uz", "expected_uz", "relative_error")}}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        m = out.get("mesh") or {}
        print("网格  ：%s 节点 / %s 单元 / 倒置 %s / 体积 %s mm³"
              % (m.get("nodes"), m.get("tets"), m.get("inverted"), m.get("volume")))
        area_eff = out.get("area_effective") or area
        print("载荷  ：%.1f N 于 %.3g mm²（网格有效 %.4g，几何近似误差 %.3f%%）→ σ = %.3f MPa"
              % (args.force, area, area_eff, (out.get("area_error") or 0) * 100,
                 args.force / area_eff))
        if solved:
            print("实测  ：uz = %.7g mm" % abs(out["measured_uz"]))
            print("理论  ：uz = FL/(EA) = %.7g mm" % out["expected_uz"])
            print("相对误差：%.3e（容差 %.1e）" % (out["relative_error"], out.get("tol", 1e-6)))
        else:
            print("未解出：%s" % (out.get("run") or {}).get("stdout_tail", [])[-4:])
        print("结论  ：%s" % verdict)

    if not solved:
        return 1
    return 0 if verdict in ("ok", "poisson_constraint") else 1


if __name__ == "__main__":
    sys.exit(main())
