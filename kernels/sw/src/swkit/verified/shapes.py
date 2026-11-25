"""把平面点列拉成实体：齿轮、链轮这类轮廓走这里。"""

from __future__ import annotations

import math
import sys
from typing import Any, Dict, Sequence, Tuple

from ..core.com import none_dispatch
from ._common import com_doc
from .features import _volume_mm3, extrude, shape_counts
from .sketch_ops import create_sketch, line

Point = Tuple[float, float]


def _gapfill():
    root = os_path()
    if root not in sys.path:
        sys.path.insert(0, root)
    import gapfill
    return gapfill


def os_path() -> str:
    import os
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 5, "design"))


def extrude_polygon(doc: Any, points: Sequence[Point], depth_mm: float,
                    tool: str) -> Dict[str, Any]:
    """用折线封闭轮廓做拉伸。判据是体积大于 0，且不超过外接圆的圆柱。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": tool, "api": "SketchManager.CreateLine + FeatureExtrusion3",
        "status": "unverified", "detail": {"points": len(points), "depth_mm": depth_mm},
        "checks": {},
    }
    if len(points) < 3 or depth_mm <= 0:
        out["detail"]["error"] = "至少三个点，厚度必须为正"
        return out
    radius = max(math.hypot(x, y) for x, y in points)
    before = shape_counts(doc)
    try:
        create_sketch(doc)
        closed = list(points) + [points[0]]
        for start, end in zip(closed, closed[1:]):
            line(doc, start[0], start[1], end[0], end[1])
        made = extrude(doc, depth_mm)
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    volume = _volume_mm3(doc)
    cylinder = math.pi * radius * radius * depth_mm
    after = shape_counts(doc)
    checks = {
        "feature_added": after["features"] > before["features"],
        "extrude_ok": bool(made.get("ok")),
        "volume_positive": volume is not None and volume > 1.0,
        "inside_tip_cylinder": volume is not None and volume < cylinder * 1.02,
    }
    out["checks"] = checks
    out["detail"].update({
        "volume_mm3": volume,
        "tip_cylinder_mm3": round(cylinder, 3),
        "extrude": made.get("checks"),
    })
    out["ok"] = all(checks.values())
    out["status"] = "verified" if out["ok"] else "unverified"
    return out


def gear(doc: Any, module: float = 2.0, teeth: int = 12, thickness_mm: float = 8.0) -> Dict[str, Any]:
    points = _gapfill().spur_gear_polygon(module, teeth)
    result = extrude_polygon(doc, points, thickness_mm, "sw_spur_gear")
    result["detail"]["module"] = module
    result["detail"]["teeth"] = teeth
    return result


def sprocket(doc: Any, teeth: int = 12, pitch_mm: float = 12.7, thickness_mm: float = 6.0) -> Dict[str, Any]:
    gap = _gapfill()
    diameter = gap.sprocket_pitch_diameter(teeth, pitch_mm)
    # 近似齿：节圆外侧为齿顶，内侧为齿根，不是生产用齿形。
    outer = diameter / 2.0 + pitch_mm * 0.3
    root = diameter / 2.0 - pitch_mm * 0.4
    points = []
    step = 2.0 * math.pi / teeth
    for i in range(teeth):
        center = i * step
        half = step * 0.25
        points.append((outer * math.cos(center - half), outer * math.sin(center - half)))
        points.append((outer * math.cos(center + half), outer * math.sin(center + half)))
        points.append((root * math.cos(center + step * 0.5), root * math.sin(center + step * 0.5)))
    result = extrude_polygon(doc, points, thickness_mm, "sw_sprocket")
    result["detail"]["pitch_diameter_mm"] = round(diameter, 3)
    return result


def fillet_edges(doc: Any, radius_mm: float = 2.0, kind: str = "variable",
                 max_edges: int = 4) -> Dict[str, Any]:
    """uniform / variable / full_round。判据和普通圆角一样：面数增加且体积下降。"""
    from .features import _select_all_edges
    kind_code = {"uniform": 0, "variable": 1, "full_round": 3}.get(kind)
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_fillet_edges", "api": "FeatureFillet3",
        "status": "unverified", "detail": {"kind": kind, "radius_mm": radius_mm},
        "checks": {},
    }
    if kind_code is None:
        out["detail"]["error"] = "kind 只能是 uniform / variable / full_round"
        return out
    before = shape_counts(doc)
    selected = _select_all_edges(doc, max_edges)
    if selected == 0:
        out["detail"]["error"] = "没选中任何边"
        return out
    volume_before = _volume_mm3(doc)
    try:
        _sw, md = com_doc()
        md.FeatureManager.FeatureFillet3(
            2, float(radius_mm) / 1000.0, float(radius_mm) / 2000.0, 0.0,
            kind_code, 0, 0, None, None, None, None, None, None, None)
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    volume_after = _volume_mm3(doc)
    dropped = (volume_before is not None and volume_after is not None
               and volume_after < volume_before - 0.1)
    checks = {
        "edges_selected": selected > 0,
        "faces_increased": after["faces"] > before["faces"],
        "volume_dropped": bool(dropped),
    }
    out["checks"] = checks
    out["detail"].update({
        "edges_selected": selected,
        "volume_before_mm3": volume_before,
        "volume_after_mm3": volume_after,
        "null_callout": none_dispatch() is not None,
    })
    out["ok"] = all(checks.values())
    out["status"] = "verified" if out["ok"] else "unverified"
    return out
