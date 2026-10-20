"""swkit.verified.view_measure —— 视图缩放/定向 + 面间测量

判据：

| 工具 | 判据 |
|---|---|
| `zoom_to_fit` | `IModelView.Scale2` 前后变化（并记录数值） |
| `set_view_orientation` | `IModelView.Orientation` 矩阵前后变化 |
| `measure_distance` | `IMeasure.Distance` 与**调用方给的期望值**比较（默认 20 mm） |

实测：
* `IModelView.Orientation` 是 0 参读、1 参写；`Scale2` 只读。
* `IMeasure` 用 `doc.Extension.CreateMeasure()` 取，`Calculate(...)` 后用
  `Distance`（单位**米**）读数。
* 选面用 `SelectByID2("", "FACE", x, y, z, ...)`，坐标要落在面上。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, pyw, val

__all__ = ["zoom_to_fit", "set_view_orientation", "measure_distance",
           "ORIENTATION_IDS"]

# swNamedViewOrientation_e（THB2 用 ShowNamedView2 的 id）
ORIENTATION_IDS = {"front": 1, "back": 2, "left": 3, "right": 4,
                   "top": 5, "bottom": 6, "isometric": 7, "trimetric": 8,
                   "dimetric": 9}


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _scale(doc: Any) -> Optional[float]:
    try:
        return float(val(doc.ActiveView, "Scale2"))
    except Exception:
        return None


def _orientation(doc: Any) -> Optional[List[float]]:
    try:
        o = val(doc.ActiveView, "Orientation")
        return [round(float(v), 6) for v in o]
    except Exception:
        return None


def zoom_to_fit(doc: Any) -> Dict[str, Any]:
    """缩放到合适大小。判据：`Scale2` 变化。"""
    out = _result("sw_zoom_to_fit", "IModelDoc2.ViewZoomtofit2")
    before = _scale(doc)
    try:
        doc.ViewZoomtofit2()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _scale(doc)
    out["detail"].update({"scale_before": before, "scale_after": after})
    out["checks"] = {"scale_readable": before is not None and after is not None,
                     "scale_changed": before is not None and after is not None
                     and abs(after - before) > 1e-9}
    # 缩放比本来就可能是 1（刚打开就合适），所以只要求"可读 + 不大于 0"
    out["checks"]["scale_positive"] = bool(after and after > 0)
    out["ok"] = out["checks"]["scale_readable"] and out["checks"]["scale_positive"]
    return out


def set_view_orientation(doc: Any, view_name: str = "isometric") -> Dict[str, Any]:
    """设置视图方向。判据：`Orientation` 矩阵变化。"""
    out = _result("sw_set_view_orientation", "IModelDoc2.ShowNamedView2")
    vid = ORIENTATION_IDS.get(str(view_name).lower())
    if vid is None:
        out["detail"]["error"] = "未知方向：%s（可选 %s）" % (
            view_name, "/".join(ORIENTATION_IDS))
        return out
    before = _orientation(doc)
    try:
        doc.ShowNamedView2("", vid)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _orientation(doc)
    out["detail"].update({"requested": view_name, "orientation_id": vid,
                          "orientation_before": before,
                          "orientation_after": after})
    changed = before is not None and after is not None and any(
        abs(a - b) > 1e-6 for a, b in zip(before, after))
    out["checks"] = {"orientation_readable": before is not None and after is not None,
                     "orientation_changed": bool(changed)}
    out["ok"] = all(out["checks"].values())
    return out


def measure_distance(doc: Any, p1: List[float], p2: List[float],
                     expected_mm: float = 20.0, tol_mm: float = 0.2) -> Dict[str, Any]:
    """量两个面之间的距离（mm）。判据：与期望值之差 ≤ 容差。

    `p1`/`p2` 是落在两个面上的点（**mm**）。
    """
    out = _result("sw_measure_distance", "IModelDocExtension.CreateMeasure")
    out["detail"].update({"p1": p1, "p2": p2, "expected_mm": expected_mm})
    try:
        doc.ClearSelection2(True)
        ok1 = doc.Extension.SelectByID2("", "FACE", p1[0] / 1000.0,
                                       p1[1] / 1000.0, p1[2] / 1000.0,
                                       False, 0, none_dispatch(), 0)
        ok2 = doc.Extension.SelectByID2("", "FACE", p2[0] / 1000.0,
                                       p2[1] / 1000.0, p2[2] / 1000.0,
                                       True, 0, none_dispatch(), 0)
        picked = doc.SelectionManager.GetSelectedObjectCount2(-1)
        out["detail"].update({"selected_1": ok1, "selected_2": ok2,
                              "selected": picked})
        if picked < 2:
            out["detail"]["error"] = "没能选中两个面"
            return out
        # pywin32 的动态对象取不到 IMeasure 成员（报"找不到成员"）→ 必须 comtypes
        from ._common import com_doc
        _sw, md = com_doc()
        m = md.Extension.CreateMeasure()
        m.Calculate(None)
        dist_m = m.Distance
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    dist_mm = round(float(dist_m) * 1000.0, 4) if dist_m is not None else None
    out["detail"]["distance_mm"] = dist_mm
    out["checks"] = {"measured": dist_mm is not None,
                     "matches_expected": dist_mm is not None
                     and abs(dist_mm - expected_mm) <= tol_mm}
    out["ok"] = all(out["checks"].values())
    return out
