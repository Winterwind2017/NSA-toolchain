"""焊件。只承认特征树里读回来的结果，不返回示例切割清单。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ..core.com import val
from ._common import com_doc, count_features, iter_features

__all__ = ["insert_weldment", "structural_member", "read_cut_list", "judge_feature"]


def judge_feature(before: int, after: int, new_types: List[str], needle: str) -> Dict[str, bool]:
    return {
        "feature_added": after > before,
        "type_matches": any(needle in str(name).lower() for name in new_types),
    }


def _new_types(doc: Any, before: set) -> List[str]:
    return [str(val(feat, "GetTypeName2")) for feat in iter_features(doc)
            if str(val(feat, "GetTypeName2")) not in before]


def insert_weldment(doc: Any) -> Dict[str, Any]:
    """插入焊件特征。本机类型库里 InsertWeldmentFeature 没有参数。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_insert_weldment",
        "api": "IFeatureManager.InsertWeldmentFeature",
        "status": "unverified", "detail": {}, "checks": {},
    }
    before_n = count_features(doc)
    before = {str(val(feat, "GetTypeName2")) for feat in iter_features(doc)}
    try:
        _sw, md = com_doc()
        returned = md.FeatureManager.InsertWeldmentFeature()
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    out["detail"]["returned_type"] = type(returned).__name__
    new_types = _new_types(doc, before)
    checks = judge_feature(before_n, count_features(doc), new_types, "weldment")
    out["checks"] = checks
    out["detail"]["new_types"] = new_types
    out["ok"] = all(checks.values())
    return out


def structural_member(doc: Any, profile_path: str, configuration: str = "Default") -> Dict[str, Any]:
    """沿当前草图的线段放结构构件。轮廓文件必须真实存在。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_structural_member",
        "api": "IFeatureManager.InsertStructuralWeldment5",
        "status": "unverified", "detail": {"profile": profile_path}, "checks": {},
    }
    if not profile_path or not os.path.isfile(profile_path):
        out["detail"]["error"] = "轮廓文件不存在"
        out["checks"] = {"profile_exists": False}
        return out
    sketch = val(doc, "SketchManager")
    active = val(sketch, "ActiveSketch") if sketch is not None else None
    segments = list(val(active, "GetSketchSegments") or []) if active is not None else []
    if not segments:
        out["detail"]["error"] = "需要一条已经画好的草图线段"
        out["checks"] = {"profile_exists": True, "has_segments": False}
        return out
    before_n = count_features(doc)
    before = {str(val(feat, "GetTypeName2")) for feat in iter_features(doc)}
    try:
        group = doc.FeatureManager.CreateStructuralMemberGroup()
        group.Segments = segments
        doc.FeatureManager.InsertStructuralWeldment5(
            profile_path, 0, False, [group], configuration or "Default")
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["checks"] = {"profile_exists": True, "has_segments": True, "feature_added": False}
        return out
    new_types = _new_types(doc, before)
    checks = judge_feature(before_n, count_features(doc), new_types, "structural")
    checks["profile_exists"] = True
    checks["has_segments"] = True
    out["checks"] = checks
    out["detail"]["new_types"] = new_types
    out["ok"] = checks["feature_added"] and checks["type_matches"]
    return out


def read_cut_list(doc: Any) -> Dict[str, Any]:
    """读焊件切割清单特征。没有清单就失败，不编一条方管。"""
    rows = []
    for feat in iter_features(doc):
        kind = str(val(feat, "GetTypeName2"))
        if "cutlist" not in kind.lower() and "weldmentcutlist" not in kind.lower():
            continue
        rows.append({"name": str(val(feat, "Name")), "type": kind})
    return {
        "ok": bool(rows),
        "tool": "sw_weldment_cut_list",
        "api": "IFeature.GetTypeName2",
        "status": "unverified",
        "items": rows,
        "checks": {"cut_list_present": bool(rows)},
        "errors": [] if rows else ["没有切割清单特征"],
    }
