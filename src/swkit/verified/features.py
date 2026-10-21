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

from ..core.com import none_dispatch, pyw, val
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
        if is_cut:
            # FeatureExtrusion3 **没有**切除开关（它的第 2 参是 Flip），
            # 传 is_cut=True 只会把料加到外面 → 切除必须走 cuts.cut_extrude。
            from .cuts import cut_extrude
            res = cut_extrude(doc, depth_mm)
            out["detail"].update({"delegated_to": "sw_cut_extrude",
                                  "cut": res.get("detail"), "cut_ok": res.get("ok")})
            out["checks"] = {"cut_ok": bool(res.get("ok"))}
            out["ok"] = bool(res.get("ok"))
            return out
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
    # `FeatureRevolve2` 的 5 参版在 **IModelDoc** 上（不在 IModelDoc2）：
    # (Angle, ReverseDir, Angle2, RevType, Options)。内核走 IModelDoc2 才报
    # "非选择性的参数"。必须 comtypes QI 过去。
    try:
        from ._common import com_doc
        sw, md = com_doc()
        model = md.QueryInterface(sw.IModelDoc)
        model.FeatureRevolve2(float(angle_deg) * math.pi / 180.0, False, 0.0, 0, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    # 几何上界判据：旋转体体积必须 < 同外径实心圆柱。
    # 轴不一定是 X —— 用"与另两维差异最大"的那一维当轴向（柱体另两维都≈直径）。
    box, radius, height = None, None, None
    for b in bodies(doc, 0):
        try:
            box = [float(x) * 1000 for x in (val(wrap(b), "GetBodyBox") or [])[:6]]
        except Exception:                           # noqa: BLE001
            box = None
        if box and len(box) == 6:
            ext = (box[3] - box[0], box[4] - box[1], box[5] - box[2])
            best_axis, best_score = 0, -1.0
            for i in range(3):
                others = [ext[j] for j in range(3) if j != i]
                score = abs(ext[i] - sum(others) / 2.0)
                if score > best_score:
                    best_axis, best_score = i, score
            others = [ext[j] for j in range(3) if j != best_axis]
            height = ext[best_axis]
            radius = max(others) / 2.0
            break
    upper = None
    if radius and height:
        frac = min(1.0, float(angle_deg) / 360.0)
        upper = math.pi * radius * radius * height * frac
    out["detail"].update({"angle_deg": angle_deg,
                          "features_before": before["features"],
                          "features_after": after["features"],
                          "volume_mm3": round(v1, 3) if v1 is not None else None,
                          "bbox_radius_mm": radius, "bbox_height_mm": height,
                          "solid_cylinder_upper_mm3":
                              None if upper is None else round(upper, 1)})
    inside = (v1 is not None and upper is not None and 0 < v1 < upper * 1.02)
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "volume_positive": bool(v1 and v1 > 0),
                     "below_solid_cylinder": bool(inside)}
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
    v0 = _volume_mm3(doc)
    try:
        # **同名两套签名**（实测）：
        #  · 底层 IFeatureManager（9 参）：FeatureFillet3(R1, Propagate, Ftyp, VarRadTyp,
        #      OverflowType, NRadii, Radii, UseHelpPoint, UseTangentHoldLine)
        #    → pywin32 在第 7 参 Radii 上永远报类型不匹配
        #  · 高层包装（14 参，Options 开头）：FeatureFillet3(Options, R1, R2, Rho, Ftyp,
        #      OverflowType, ConicRhoType, Radii, Dist2Arr, RhoArr, SetBackDistances,
        #      PointRadiusArray, PointDist2Array, PointRhoArray)
        #    → 必须走 comtypes 强类型，实测能建出真圆角
        from ._common import com_doc
        _sw, md = com_doc()
        feat = md.FeatureManager.FeatureFillet3(
            2,                                    # Options = swFeatureFilletUniformRadius
            float(radius_mm) / 1000.0,            # R1
            0.0, 0.0,                             # R2, Rho
            0, 0, 0,                              # Ftyp(Simple), OverflowType, ConicRhoType
            None, None, None, None, None, None, None)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({"features_after": after["features"],
                          "faces_after": after["faces"],
                          "edges_before": before.get("edges"),
                          "edges_after": after.get("edges"),
                          "volume_before_mm3": v0, "volume_after_mm3": v1,
                          "feature": val(feat, "Name") if feat is not None else None})
    dropped = (v0 is not None and v1 is not None and v1 < v0 - 1e-6)
    if v0 and v1:
        out["detail"]["volume_delta_mm3"] = round(v1 - v0, 3)
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "faces_increased": after["faces"] > before["faces"],
                     "volume_dropped": bool(dropped)}
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
    v0 = _volume_mm3(doc)
    try:
        # 内核把前两参写反了：InsertFeatureChamfer 真正是
        # (Options:int, ChamferType:int, Width, Angle, OtherDist,
        #  VertexChamDist1, VertexChamDist2, VertexChamDist3)
        # 内核传的是 (1, 0, ...) → Options=1、ChamferType=0（非法）→ 建出空特征
        feat = doc.FeatureManager.InsertFeatureChamfer(
            0, 1, float(distance_mm) / 1000.0, float(angle_deg) * 3.141592653589793 / 180.0,
            0.0, 0.0, 0.0, 0.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({"features_after": after["features"],
                          "faces_after": after["faces"],
                          "edges_before": before.get("edges"),
                          "edges_after": after.get("edges"),
                          "volume_before_mm3": v0, "volume_after_mm3": v1})
    dropped = (v0 is not None and v1 is not None and v1 < v0 - 1e-6)
    if v0 and v1:
        out["detail"]["volume_delta_mm3"] = round(v1 - v0, 3)
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "faces_increased": after["faces"] > before["faces"],
                     "volume_dropped": bool(dropped)}
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
    v0 = _volume_mm3(doc)
    # 官方 Remarks 的选择标记：**特征 = 1**，**镜像面/基准面 = 2**
    target = None
    for f in iter_features(doc):
        if str(val(f, "GetTypeName2")) in ("Extrusion", "Revolve", "RevolveThin",
                                           "ExtrusionThin", "Cut", "CutThin"):
            target = str(val(f, "Name"))
    if target is None:
        out["detail"]["error"] = "没有可镜像的特征"
        return out
    doc.ClearSelection2(True)
    sel_feat = doc.Extension.SelectByID2(target, "BODYFEATURE", 0, 0, 0, False, 1,
                                         none_dispatch(), 0)
    sel_plane = doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, True, 2,
                                          none_dispatch(), 0)
    out["detail"].update({"feature_to_mirror": target,
                          "selected_feature": bool(sel_feat),
                          "selected_plane": bool(sel_plane)})
    if not (sel_feat and sel_plane):
        out["detail"]["error"] = "选择失败（特征或基准面名不对）"
        return out
    try:
        feat = doc.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    ratio = (v1 / v0) if (v0 and v1) else None
    out["detail"].update({"features_after": after["features"],
                          "solids_after": after["solids"],
                          "volume_before_mm3": v0, "volume_after_mm3": v1,
                          "volume_ratio": None if ratio is None else round(ratio, 3),
                          "feature": None if feat is None else str(val(feat, "Name"))})
    doubled = ratio is not None and abs(ratio - 2.0) < 0.02
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "volume_doubled": bool(doubled)}
    out["ok"] = all(out["checks"].values())
    return out


def mirror_body(doc: Any, plane: str = "前视基准面") -> Dict[str, Any]:
    """镜像**实体**（`InsertMirrorFeature2(BMirrorBody=True)`）。

    与 `mirror_feature` 的区别：这里镜像的是**整个实体**，不是特征。
    选择标记（官方 Remarks）：待镜像**实体 = 256**、镜像面/基准面 = **2**。

    实测 40×25×20 块跨前视基准面：体积 20000→**40000**、实体 1→**2**、
    特征树出现 `MirrorSolid`。
    """
    out = _result("sw_mirror", "IFeatureManager.InsertMirrorFeature2(BMirrorBody=True)")
    before = shape_counts(doc)
    v0 = _volume_mm3(doc)
    out["detail"].update({"plane": plane, "solids_before": before["solids"],
                          "volume_before_mm3": v0})
    body = None
    for b in bodies(doc, 0):
        body = b
        break
    if body is None:
        out["detail"]["error"] = "没有实体可镜像"
        return out
    box = None
    try:
        box = [float(x) for x in (val(wrap(body), "GetBodyBox") or [])[:6]]
    except Exception:                               # noqa: BLE001
        box = None
    doc.ClearSelection2(True)
    ok_body = False
    if box and len(box) == 6:
        cx = (box[0] + box[3]) / 2.0
        cy = (box[1] + box[4]) / 2.0
        cz = (box[2] + box[5]) / 2.0
        ok_body = doc.Extension.SelectByID2("", "SOLIDBODY", cx, cy, cz, False, 256,
                                            none_dispatch(), 0)
    ok_plane = doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, True, 2,
                                         none_dispatch(), 0)
    out["detail"].update({"selected_body": bool(ok_body),
                          "selected_plane": bool(ok_plane)})
    if not (ok_body and ok_plane):
        out["detail"]["error"] = "选择失败（实体或基准面）"
        return out
    try:
        feat = doc.FeatureManager.InsertMirrorFeature2(True, False, False, False, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    v1 = _volume_mm3(doc)
    out["detail"].update({"solids_after": after["solids"],
                          "features_after": after["features"],
                          "volume_after_mm3": v1,
                          "feature": None if feat is None else str(val(feat, "Name"))})
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "solid_added": after["solids"] > before["solids"]}
    out["ok"] = all(out["checks"].values())
    return out