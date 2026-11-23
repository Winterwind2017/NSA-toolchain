"""参数扫描：改一个尺寸跑一串工况，输出曲线并与"许用值"反查。

非标选型真正要回答的不是"这个尺寸够不够"，而是"**改到多少才够**"。
所以这里除了扫表，还提供 `pick_min()`：给定许用挠度/许用应力，返回最小可行值。

判据分成两层：
* 每一点仍与闭式解对账（沿用 brep_bridge 的 axial_part / cantilever_part）；
* 汇总层看**单调性**——尺寸变大、位移/应力必须变小，否则说明扫的参数没落在
  正确的方向（写错参数名最容易犯这个错）。
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .brep_bridge import axial_part, cantilever_part
from .mesh import FeaError


@dataclass
class Point:
    value: float
    ok: bool
    measured: float
    expected: float
    relative_error: float
    stress_nominal: float
    slenderness: float
    volume_error: float
    error: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "ok": self.ok,
                "measured": self.measured, "expected": self.expected,
                "relative_error": self.relative_error,
                "stress_nominal": self.stress_nominal,
                "slenderness": self.slenderness,
                "volume_error": self.volume_error, "error": self.error}


@dataclass
class Sweep:
    param: str
    case: str
    points: List[Point] = field(default_factory=list)

    def ok_points(self) -> List[Point]:
        return [p for p in self.points if p.ok]

    def monotonic(self, decreasing: bool = True) -> bool:
        """尺寸↑ 时位移/应力应↓（decreasing=True）。只对 ok 点判。"""
        vals = [p.measured if decreasing else p.stress_nominal for p in self.ok_points()]
        return all(a >= b - 1e-15 for a, b in zip(vals, vals[1:])) if decreasing else all(
            a >= b - 1e-15 for a, b in zip(vals, vals[1:]))

    def to_text(self) -> str:
        head = "%-10s %-6s %-13s %-13s %-9s %-11s" % (
            self.param, "ok", "measured", "expected", "err%", "stress(MPa)")
        lines = ["扫描 %s（case=%s）" % (self.param, self.case), head]
        for p in self.points:
            if p.error:
                lines.append("%-10g %-6s %s" % (p.value, "-", p.error))
                continue
            lines.append("%-10g %-6s %-13.6e %-13.6e %-9.3f %-11.4f"
                         % (p.value, "yes" if p.ok else "NO", p.measured, p.expected,
                            p.relative_error * 100, p.stress_nominal))
        return "\n".join(lines)

    def to_csv(self, path: str) -> str:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            raise FeaError("CSV 父目录不存在：%s" % d)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["param", "value", "ok", "measured", "expected",
                         "relative_error", "stress_nominal", "slenderness",
                         "volume_error", "error"])
            for p in self.points:
                wr.writerow([self.param, p.value, int(p.ok), "%.9g" % p.measured,
                             "%.9g" % p.expected, "%.6g" % p.relative_error,
                             "%.6g" % p.stress_nominal, "%.6g" % p.slenderness,
                             "%.6g" % p.volume_error, p.error])
        return path


def sweep(*, factory: Callable[[float], object], param: str, values: Sequence[float],
          case: str, force: float, E: float, nu: float, mesh_size: float,
          order: int = 2, tol: float, workdir: str,
          kwargs: Optional[Dict[str, object]] = None) -> Sweep:
    """对 `factory(value)` 造出的零件跑 `case`，收集每点结果。

    case: "axial"（轴向拉伸）或 "cantilever"（悬臂弯曲）。
    """
    if case not in ("axial", "cantilever"):
        raise FeaError("case 只支持 axial / cantilever，得到 %r" % (case,))
    if not values:
        raise FeaError("values 不能为空")
    kw = dict(kwargs or {})
    out = Sweep(param=param, case=case)
    for v in values:
        part = factory(float(v))
        try:
            if case == "axial":
                res = axial_part(part, force=force, E=E, nu=nu, mesh_size=mesh_size,
                                 order=order, tol=tol,
                                 workdir=os.path.join(workdir, "%s_%g" % (param, v)), **kw)
            else:
                res = cantilever_part(part, force=force, E=E, nu=nu, mesh_size=mesh_size,
                                      order=order, tol=tol,
                                      workdir=os.path.join(workdir, "%s_%g" % (param, v)), **kw)
        except FeaError as exc:
            out.points.append(Point(float(v), False, 0.0, 0.0, float("inf"), 0.0, 0.0, 0.0,
                                    error=str(exc)))
            continue
        if res.get("stage") != "done":
            out.points.append(Point(float(v), False, 0.0, 0.0, float("inf"), 0.0, 0.0, 0.0,
                                    error="未解出"))
            continue
        out.points.append(Point(
            value=float(v), ok=bool(res.get("ok")),
            measured=abs(float(res["measured"])), expected=abs(float(res["expected"])),
            relative_error=float(res["relative_error"]),
            stress_nominal=float(res.get("stress_nominal") or 0.0),
            slenderness=float(res.get("slenderness") or 0.0),
            volume_error=float((res.get("part") or {}).get("volume_error") or 0.0)))
    return out


def pick_min(sw: Sweep, *, max_deflection: Optional[float] = None,
             max_stress: Optional[float] = None) -> Optional[float]:
    """返回满足许用挠度/许用应力的**最小**尺寸值；无解返回 None。

    只看解出来的点；没解出的点不能当"满足"。
    """
    if max_deflection is None and max_stress is None:
        raise FeaError("至少要给 max_deflection 或 max_stress")
    cands = []
    for p in sw.ok_points():
        if max_deflection is not None and p.measured > max_deflection:
            continue
        if max_stress is not None and p.stress_nominal > max_stress:
            continue
        cands.append(p.value)
    return min(cands) if cands else None
