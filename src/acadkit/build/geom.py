"""几何类 builder：line / circle / arc / polyline / rect / ellipse / spline / hatch。

参数由 `ctx["params"]` 覆盖（CLI 用），缺省值与判据的默认期望一致。
"""

from __future__ import annotations

import math
from typing import Any, Dict

from .helpers import add, dbl, ms_of, objs, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_circle(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(*_p(ctx, "center", (10.0, 20.0, 0.0))),
        float(_p(ctx, "radius", 25.0)), label="AddCircle")


def build_line(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    add(ms, "AddLine", pt(*_p(ctx, "start", (0.0, 0.0, 0.0))),
        pt(*_p(ctx, "end", (60.0, 0.0, 0.0))), label="AddLine")


def build_arc(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    add(ms, "AddArc", pt(*_p(ctx, "center", (0.0, 0.0, 0.0))),
        float(_p(ctx, "radius", 10.0)), float(_p(ctx, "start_angle", 0.0)),
        float(_p(ctx, "end_angle", math.pi / 2)), label="AddArc")


def build_polyline(doc: Any, ctx: Dict[str, Any]) -> None:
    pts = _p(ctx, "points", [(0, 0), (40, 0), (40, 30)])
    flat = []
    for p in pts:
        flat.extend([float(p[0]), float(p[1])])
    ms = ms_of(doc)
    pl = add(ms, "AddLightWeightPolyline", dbl(flat),
             label="AddLightWeightPolyline")
    pl.Closed = bool(_p(ctx, "closed", False))


def build_rect(doc: Any, ctx: Dict[str, Any]) -> None:
    x1, y1 = _p(ctx, "corner1", (0.0, 0.0))
    x2, y2 = _p(ctx, "corner2", (40.0, 30.0))
    ms = ms_of(doc)
    pl = add(ms, "AddLightWeightPolyline",
             dbl([x1, y1, x2, y1, x2, y2, x1, y2]),
             label="AddLightWeightPolyline")
    pl.Closed = True


def build_ellipse(doc: Any, ctx: Dict[str, Any]) -> None:
    center = _p(ctx, "center", (100.0, 0.0, 0.0))
    major = float(_p(ctx, "major_radius", 20.0))
    ratio = float(_p(ctx, "ratio", 0.5))
    ms = ms_of(doc)
    add(ms, "AddEllipse", pt(*center), pt(major, 0.0, 0.0), ratio,
        label="AddEllipse")


def build_spline(doc: Any, ctx: Dict[str, Any]) -> None:
    pts = _p(ctx, "points", [(0, 50), (20, 60), (40, 55), (60, 70)])
    flat = []
    for p in pts:
        flat.extend([float(p[0]), float(p[1]), 0.0])
    ms = ms_of(doc)
    add(ms, "AddSpline", dbl(flat), pt(0, 0, 0), pt(0, 0, 0), label="AddSpline")


def build_hatch(doc: Any, ctx: Dict[str, Any]) -> None:
    """闭合多段线作外环 → HATCH（ANSI31）→ Evaluate。"""
    x1, y1 = _p(ctx, "corner1", (0.0, 100.0))
    x2, y2 = _p(ctx, "corner2", (40.0, 130.0))
    pattern = str(_p(ctx, "pattern", "ANSI31"))
    ms = ms_of(doc)
    pl = add(ms, "AddLightWeightPolyline",
             dbl([x1, y1, x2, y1, x2, y2, x1, y2]),
             label="AddLightWeightPolyline")
    pl.Closed = True
    hatch = add(ms, "AddHatch", 0, pattern, True, label="AddHatch")
    hatch.AppendOuterLoop(objs([pl]))
    hatch.Evaluate()
