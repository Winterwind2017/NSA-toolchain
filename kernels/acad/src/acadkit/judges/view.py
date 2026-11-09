"""视图判据：ZoomExtents 后视图必须把整张图包进去。"""

from __future__ import annotations

from typing import Any, Dict

from .base import Readback, num, verdict


def judge_zoom(rb: Readback, *, center, radius: float) -> Dict[str, Any]:
    view = rb.memory.meta.get("view") or {}
    c = view.get("center")
    size = num(view.get("size"))
    cx, cy = float(center[0]), float(center[1])
    checks: Dict[str, bool] = {
        "view_read": bool(c) and size is not None,
        "covers_geometry": bool(size is not None and size >= 2.0 * radius * 0.95),
        "centered": bool(c and abs(float(c[0]) - cx) <= radius * 0.35
                         and abs(float(c[1]) - cy) <= radius * 0.35),
    }
    detail = {"view_center": c, "view_size": size,
              "expected_center": [cx, cy], "expected_min_size": 2 * radius * 0.95,
              "view_dir": view.get("dir")}
    return verdict(checks, detail, {"view": view})
