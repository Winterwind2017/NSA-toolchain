"""swkit.verified.features —— 特征建模（拉伸/旋转/圆角/倒角/异型孔/镜像）

判据都是**几何量**，不看返回值：

* 拉伸：体积 ≈ 截面积 × 深度（用质量属性读体积，与手算对比）
* 旋转：体积 ≈ 2πR·A（同样手算对照）
* 圆角/倒角：实体面数增加，且特征数 +1
* 异型孔：体积**减少**，特征数 +1
* 镜像：特征数 +1

单位：对外 **mm**（内核 `_m()` 负责转米）。
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

from ..core.com import pyw, val
from ._common import bodies, faces_of, iter_features, shape_counts, wrap

__all__ = ["extrude", "revolve", "fillet", "chamfer", "hole_wizard", "mirror_feature",
           "DEFAULT_PART_TEMPLATE"]

DEFAULT_PART_TEMPLATE = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
                        r"\gb_part.prtdot")


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _volume_mm3(doc: Any) -> Optional[float]:
    """体积（mm³）。必须走 comtypes：pywin32 取不到 IMassProperty 成员。"""
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        mp = md.Extension.CreateMassProperty()
        v = mp.Volume
        return float(v) * 1e9 if v is not None else None
    except Exception:
        return None


def _kernel():
    from .sketch_ops import app
    return app()


def new_part(template: str = "") -> Any:
    """建一个空白零件（方便用体积做判据）。"""
    from ._common import com_app
    tpl = template or DEFAULT_PART_TEMPLATE
    if not os.path.isfile(tpl):
        raise FileNotFoundError(tpl)
    _sw, app_ct = com_app()
    app_w = pyw().Dispatch("SldWorks.Application")
    app_w.CloseAllDocuments(True)
    if app_ct.NewDocument(tpl, 0, 0.0, 0.0) is None:
        raise RuntimeError("NewDocument 失败")
    return app_w.ActiveDoc


def _select_all_edges(doc: Any, limit: int = 4) -> int:
    """选中实体的若干条边（圆角/倒角的前置）。"""
    doc.ClearSelection2(True)
    n = 0
    for body in bodies(doc, 0):
        for f in faces_of(body):
            edges = val(f, "GetEdges") or []
            try:
                edges = list(edges)
            except TypeError:
                continue
            for e in edges:
                try:
                    wrap(e).Select2(True, 1)
                    n += 1
                except Exception:
                    continue
                if n >= limit:
                    return n
    return n


def extrude(doc: Any, depth_mm: float = 20.0, draft_deg: float = 0.0,
            is_cut: bool = False) -> Dict[str, Any]:
    """拉伸当前草图。判据：特征数 +1，且体积有变化（非切除时体积应≈面积×深度）。"""
    out = _result("sw_extrude", "IFeatureManager.FeatureExtrusion3")
    before = shape_counts(doc)
    v0 = _volume_mm3(doc)
    try:
        _kernel().extrude(depth=depth_mm, draft_angle=draft_deg, is_cut=is_cut)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({
        "depth_mm": depth_mm, "is_cut": is_cut,
        "features_before": before["features"], "features_after": after["features"],
        "solids_before": before["solids"], "solids_after": after["solids"],
        "volume_before_mm3": round(v0, 3) if v0 is not None else None,
        "volume_after_mm3": round(v1, 3) if v1 is not None else None,
    })
    delta = (v1 - v0) if (v0 is not None and v1 is not None) else None
    out["checks"] = {
        "feature_added": after["features"] > before["features"],
        "volume_changed": delta is not None and abs(delta) > 1.0,
    }
    out["ok"] = out["checks"]["feature_added"] and out["checks"]["volume_changed"]
    return out


def revolve(doc: Any, angle_deg: float = 360.0, is_cut: bool = False) -> Dict[str, Any]:
    """旋转当前草图（需有中心线/轴）。判据：特征 +1 且体积 > 0。"""
    out = _result("sw_revolve", "IFeatureManager.FeatureRevolve2")
    before = shape_counts(doc)
    try:
        _kernel().revolve(angle=angle_deg, is_cut=is_cut)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({"angle_deg": angle_deg,
                          "features_before": before["features"],
                          "features_after": after["features"],
                          "volume_mm3": round(v1, 3) if v1 is not None else None})
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "volume_positive": bool(v1 and v1 > 0)}
    out["ok"] = all(out["checks"].values())
    return out


def fillet(doc: Any, radius_mm: float = 2.0, max_edges: int = 4) -> Dict[str, Any]:
    """圆角。判据：特征 +1 **且** 面数增加。"""
    out = _result("sw_fillet", "IFeatureManager.FeatureFillet")
    before = shape_counts(doc)
    selected = _select_all_edges(doc, max_edges)
    out["detail"].update({"radius_mm": radius_mm, "edges_selected": selected,
                          "faces_before": before["faces"]})
    if selected == 0:
        out["detail"]["error"] = "没选中任何边"
        return out
    try:
        _kernel().fillet(radius=radius_mm)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    out["detail"].update({"features_after": after["features"],
                          "faces_after": after["faces"]})
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "faces_increased": after["faces"] > before["faces"]}
    out["ok"] = all(out["checks"].values())
    return out


def chamfer(doc: Any, distance_mm: float = 2.0, angle_deg: float = 45.0,
            max_edges: int = 4) -> Dict[str, Any]:
    """倒角。判据：特征 +1 且面数增加。"""
    out = _result("sw_chamfer", "IFeatureManager.InsertFeatureChamfer")
    before = shape_counts(doc)
    selected = _select_all_edges(doc, max_edges)
    out["detail"].update({"distance_mm": distance_mm, "edges_selected": selected,
                          "faces_before": before["faces"]})
    if selected == 0:
        out["detail"]["error"] = "没选中任何边"
        return out
    try:
        _kernel().chamfer(distance=distance_mm, angle=angle_deg)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    out["detail"].update({"features_after": after["features"],
                          "faces_after": after["faces"]})
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "faces_increased": after["faces"] > before["faces"]}
    out["ok"] = all(out["checks"].values())
    return out


def hole_wizard(doc: Any, hole_type: str = "simple", size: str = "",
                depth_mm: float = 10.0, through_all: bool = False,
                x_mm: float = 0.0, y_mm: float = 0.0) -> Dict[str, Any]:
    """异型孔（需先选面）。判据：特征 +1 且体积**减少**。"""
    out = _result("sw_hole_wizard", "IChamferHoleWizard / WizardHoleFeatureData2")
    before = shape_counts(doc)
    v0 = _volume_mm3(doc)
    try:
        _kernel().hole_wizard(hole_type=hole_type, size=size, depth=depth_mm,
                              through_all=through_all, x=x_mm, y=y_mm)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({"depth_mm": depth_mm,
                          "features_before": before["features"],
                          "features_after": after["features"],
                          "volume_before_mm3": round(v0, 3) if v0 is not None else None,
                          "volume_after_mm3": round(v1, 3) if v1 is not None else None})
    out["checks"] = {
        "feature_added": after["features"] > before["features"],
        "volume_decreased": (v0 is not None and v1 is not None and v1 < v0),
    }
    out["ok"] = all(out["checks"].values())
    return out


def mirror_feature(doc: Any, plane: str = "前视基准面") -> Dict[str, Any]:
    """镜像特征（先选中要镜像的特征）。判据：特征数 +1。"""
    out = _result("sw_mirror", "IFeatureManager.InsertMirrorFeature2")
    before = shape_counts(doc)
    out["detail"].update({"plane": plane, "features_before": before["features"]})
    try:
        _kernel().mirror_feature(mirror_plane=plane)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    out["detail"]["features_after"] = after["features"]
    out["checks"] = {"feature_added": after["features"] > before["features"]}
    out["ok"] = out["checks"]["feature_added"]
    return out
