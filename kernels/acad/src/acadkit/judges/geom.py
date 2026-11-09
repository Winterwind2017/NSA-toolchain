"""几何图元判据（JUDGE_SPEC 2.1）。

四级逐条落：

    L1 实体数 = before + 1
    L2 类型 + 关键几何属性读回
    L3 面积/长度手算对照（圆 area≈πR²、矩形 area=w×h、线 length=√Δ²）
    L4 存盘重开后同样的 L2/L3 仍成立
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from .base import (Entity, Readback, close, new_entities, num, pt3, pt_close,
                   rel_close, reopen_check, verdict)


def _new_one(rb: Readback, type_name: str) -> Optional[Entity]:
    new = new_entities(rb, type_name)
    return new[0] if len(new) == 1 else None


def _count_ok(rb: Readback, type_name: str) -> bool:
    return (rb.memory.count(type_name) == rb.before.count(type_name) + 1
            and len(new_entities(rb, type_name)) == 1)


def _units(rb: Readback) -> Dict[str, Any]:
    scale = rb.memory.unit_scale_mm
    return {"mm_per_du": scale,
            "unit_note": ("INSUNITS=%s" % rb.memory.insunits)}


def _mm(v: Optional[float], rb: Readback) -> Optional[float]:
    scale = rb.memory.unit_scale_mm
    if v is None or scale is None:
        return None
    return round(v * scale, 6)


# ── 圆 ──────────────────────────────────────────────────────────────
def judge_circle(rb: Readback, *, center=(0.0, 0.0, 0.0),
                 radius: float = 25.0, tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "CIRCLE")
    r = num(ent.get("Radius")) if ent else None
    area = num(ent.get("Area")) if ent else None
    expected_area = math.pi * float(radius) ** 2
    re_ok, re_detail = (reopen_check(rb, ent, ("Center", "Radius", "Area"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新圆"}}))
    checks = {
        "count": _count_ok(rb, "CIRCLE"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbCircle",
        "geometry": bool(ent) and pt_close(ent.get("Center"), center, tol)
                    and close(r, radius, tol),
        "area": rel_close(area, expected_area, 1e-6),
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "center_du": ent.get("Center") if ent else None,
        "center_expected_du": list(center),
        "radius_du": r,
        "radius_expected_du": float(radius),
        "radius_mm": _mm(r, rb),
        "area_du2": area,
        "area_expected_du2": round(expected_area, 6),
        "reopen": re_detail,
    }
    detail.update(_units(rb))
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


# ── 直线 ────────────────────────────────────────────────────────────
def judge_line(rb: Readback, *, start=(0.0, 0.0, 0.0), end=(60.0, 0.0, 0.0),
               tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "LINE")
    p0, p1 = pt3(start), pt3(end)
    expected_len = math.dist(p0, p1) if (p0 and p1) else None
    length = num(ent.get("Length")) if ent else None
    re_ok, re_detail = (reopen_check(rb, ent, ("StartPoint", "EndPoint", "Length"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新线"}}))
    checks = {
        "count": _count_ok(rb, "LINE"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbLine",
        "geometry": bool(ent) and pt_close(ent.get("StartPoint"), start, tol)
                    and pt_close(ent.get("EndPoint"), end, tol),
        "length": rel_close(length, expected_len, 1e-9),
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "start_du": ent.get("StartPoint") if ent else None,
        "end_du": ent.get("EndPoint") if ent else None,
        "length_du": length,
        "length_expected_du": round(expected_len, 9) if expected_len else None,
        "length_mm": _mm(length, rb),
        "reopen": re_detail,
    }
    detail.update(_units(rb))
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


def judge_spline(rb: Readback, *, closed: bool = False,
                 min_control_points: int = 1) -> Dict[str, Any]:
    """SPLINE：本机实测 3 个拟合点会得到 5 个控制点（AutoCAD 自动补切向控制点），
    所以只判"控制点数 >= 输入点数"，不判相等。"""
    ent = _new_one(rb, "SPLINE")
    n = num(ent.get("NumberOfControlPoints")) if ent else None
    re_ok, re_detail = (reopen_check(rb, ent, ("Closed", "NumberOfControlPoints"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新样条"}}))
    checks = {
        "count": _count_ok(rb, "SPLINE"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbSpline",
        "closed": bool(ent) and bool(ent.get("Closed")) == closed,
        "control_points": bool(n is not None and n >= min_control_points),
        "reopen": re_ok,
    }
    detail = {"handle": ent.handle if ent else None,
              "control_points": n,
              "min_control_points": min_control_points,
              "reopen": re_detail}
    return verdict(checks, detail, {"entity": ent.attrs if ent else None})


# ── 矩形（闭合 LWPOLYLINE）──────────────────────────────────────────
def judge_rect(rb: Readback, *, corner1=(0.0, 0.0), corner2=(40.0, 30.0),
               tol: float = 1e-6) -> Dict[str, Any]:
    ent = _new_one(rb, "LWPOLYLINE")
    x1, y1 = float(corner1[0]), float(corner1[1])
    x2, y2 = float(corner2[0]), float(corner2[1])
    width, height = abs(x2 - x1), abs(y2 - y1)
    expected_area = width * height
    verts = ent.get("vertices") if ent else None
    closed = bool(ent.get("Closed")) if ent else False
    area = num(ent.get("Area")) if ent else None
    want = {(round(x1, 6), round(y1, 6)), (round(x2, 6), round(y1, 6)),
            (round(x2, 6), round(y2, 6)), (round(x1, 6), round(y2, 6))}
    got = {(round(v[0], 6), round(v[1], 6)) for v in (verts or [])}
    re_ok, re_detail = (reopen_check(rb, ent, ("Closed", "Area"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新多段线"}}))
    if re_ok:
        # 顶点也要在重开后一致（Area 相同但形状可能不同）
        hit = rb.reopened.by_handle(ent.handle) if rb.reopened else None
        re_verts = {(round(v[0], 6), round(v[1], 6))
                    for v in (hit.get("vertices") or [])} if hit else set()
        re_ok = re_verts == got
        if not re_ok:
            re_detail.setdefault("mismatch", {})["vertices"] = [
                sorted(got), sorted(re_verts)]
    checks = {
        "count": _count_ok(rb, "LWPOLYLINE"),
        "type": bool(ent) and ent.get("ObjectName") == "AcDbPolyline",
        "closed": closed and len(got) == 4 and got == want,
        "area": rel_close(area, expected_area, 1e-9),
        "reopen": re_ok,
    }
    detail: Dict[str, Any] = {
        "handle": ent.handle if ent else None,
        "vertices_du": verts,
        "vertices_expected_du": sorted(want),
        "closed": closed,
        "width_du": width,
        "height_du": height,
        "area_du2": area,
        "area_expected_du2": expected_area,
        "area_mm2": _mm(area, rb),
        "reopen": re_detail,
    }
    detail.update(_units(rb))
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)
