"""swkit.verified.surfaces —— 曲面（平面/拉伸/旋转）

判据：**曲面实体数** +1（`GetBodies2(1, True)`），并记录曲面/实体数量变化。

实测归属（重要）：曲面 API **不在 IModelDoc2 上**，而在
* `IModelDoc::InsertPlanarRefSurface()`（0 参，需先选闭合草图）
* `IModelDoc::InsertRevolvedRefSurface(Angle, ReverseDir, Angle2, RevType)`（4 参）
* `IModelDoc::FeatureExtruRefSurface(...)` 15 参 / `IFeatureManager::FeatureExtruRefSurface(21)`
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from ..core.com import none_dispatch, pyw, val

__all__ = ["surface_counts", "planar_surface", "revolved_surface",
           "extruded_surface"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def surface_counts(doc: Any) -> Dict[str, int]:
    def _n(t: int) -> int:
        try:
            return len(list(doc.GetBodies2(t, True) or []))
        except Exception:
            return -1
    return {"solids": _n(0), "surfaces": _n(1)}


def planar_surface(doc: Any) -> Dict[str, Any]:
    """平面区域（需闭合草图）。判据：曲面数 +1。"""
    out = _result("sw_planar_surface", "IModelDoc.InsertPlanarRefSurface()")
    before = surface_counts(doc)
    out["detail"]["before"] = before
    try:
        # `InsertPlanarRefSurface` 在本机是**属性**：读取即执行，加括号会报
        # "TypeError: 'bool' object is not callable"。
        v = doc.InsertPlanarRefSurface
        out["detail"]["returned"] = v
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = surface_counts(doc)
    out["detail"]["after"] = after
    out["checks"] = {"surface_added": after["surfaces"] > before["surfaces"]}
    out["ok"] = out["checks"]["surface_added"]
    return out


def revolved_surface(doc: Any, angle_deg: float = 360.0) -> Dict[str, Any]:
    """旋转曲面（需草图 + 中心线）。判据：曲面数 +1。"""
    out = _result("sw_revolved_surface",
                  "IModelDoc.InsertRevolvedRefSurface(4 参)")
    before = surface_counts(doc)
    out["detail"].update({"angle_deg": angle_deg, "before": before})
    try:
        doc.InsertRevolvedRefSurface(math.radians(float(angle_deg)), False, 0.0, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = surface_counts(doc)
    out["detail"]["after"] = after
    out["checks"] = {"surface_added": after["surfaces"] > before["surfaces"]}
    out["ok"] = out["checks"]["surface_added"]
    return out


SW_END_BLIND = 0
SW_END_THROUGH_ALL = 1
SW_START_SKETCH = 0


def extruded_surface(doc: Any, depth_mm: float = 20.0,
                     through_all: bool = False) -> Dict[str, Any]:
    """拉伸曲面（需草图）。判据：曲面数 +1。

    `IModelDoc::FeatureExtruRefSurface` 是 15 参：
    Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2, Dang1, Dang2,
    OffsetReverse1, OffsetReverse2
    """
    out = _result("sw_extruded_surface",
                  "IModelDoc.FeatureExtruRefSurface(15 参)")
    before = surface_counts(doc)
    out["detail"].update({"depth_mm": depth_mm, "before": before})
    depth = float(depth_mm) / 1000.0
    try:
        # 现役 API 是 **IFeatureManager.FeatureExtruRefSurface3（22 参）**；
        # IModelDoc.FeatureExtruRefSurface（15 参）是老接口，调了返回 None 且不出曲面。
        # 官方 Remarks：调用前必须 SelectByID2 选草图（**mark 0**）。
        sk = doc.SketchManager.ActiveSketch
        name = val(sk, "Name") if sk is not None else None
        if name:
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0,
                                      none_dispatch(), 0)
        args = [
            True,           # Sd 单边
            False,          # Dir 不反转
            SW_START_SKETCH, 0.0,   # StartCond, OffsetVal
            SW_END_THROUGH_ALL if through_all else SW_END_BLIND, 0,
            depth, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,   # OffsetReverse1/2, TranslateSurface1/2
            False, False,   # CapEnd1/2（不封端 = 真曲面）
            False,          # DeleteOriginalFace
            True,           # KnitResult
        ]
        out["detail"]["param_count"] = len(args)
        feat = doc.FeatureManager.FeatureExtruRefSurface3(*args)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = surface_counts(doc)
    out["detail"].update({"after": after,
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"surface_added": after["surfaces"] > before["surfaces"]}
    out["ok"] = out["checks"]["surface_added"]
    return out
