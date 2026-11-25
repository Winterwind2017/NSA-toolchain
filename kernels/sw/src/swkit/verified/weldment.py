"""焊件。只承认特征树里读回来的结果，不返回示例切割清单。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ..core.com import none_dispatch, val
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


def _member_type(name: str) -> bool:
    low = str(name).lower()
    return "weldmember" in low or "structuralmember" in low


def _sketch_segments(doc: Any) -> List[Any]:
    """退出草图后 ActiveSketch 为空，线段在 ProfileFeature 上。"""
    sketch = val(val(doc, "SketchManager"), "ActiveSketch")
    raw = sketch.GetSketchSegments if sketch is not None else None
    if not raw:
        for feat in iter_features(doc):
            if str(val(feat, "GetTypeName2")) != "ProfileFeature":
                continue
            specific = val(feat, "GetSpecificFeature2")
            if specific is None:
                continue
            raw = specific.GetSketchSegments
            break
    if raw is None:
        return []
    if callable(raw):
        try:
            raw = raw()
        except Exception:  # noqa: BLE001
            return []
    return list(raw or [])


def _set_configuration(doc: Any, configuration: str, before_types: set) -> str:
    """把刚生成的构件改成指定规格。读回的配置名不是所请求的就当失败。"""
    from comtypes import POINTER

    _sw, md = com_doc()
    cand = val(md, "FirstFeature")
    guard = 0
    readback = ""
    null_component = POINTER(_sw.IComponent2)()
    while cand is not None and guard < 2000:
        guard += 1
        kind = str(val(cand, "GetTypeName2"))
        nxt = val(cand, "GetNextFeature")
        if kind not in before_types and _member_type(kind):
            data = val(cand, "GetDefinition")
            specific = data.QueryInterface(_sw.IStructuralMemberFeatureData)
            if not specific.AccessSelections(md, null_component):
                raise RuntimeError("AccessSelections 失败")
            try:
                specific.ConfigurationName = configuration
                if not cand.ModifyDefinition(specific, md, null_component):
                    raise RuntimeError("ModifyDefinition 返回 False")
            finally:
                try:
                    specific.ReleaseSelectionAccess()
                except Exception:  # noqa: BLE001
                    pass
            fresh = val(cand, "GetDefinition").QueryInterface(_sw.IStructuralMemberFeatureData)
            readback = str(fresh.ConfigurationName or "")
        cand = nxt
    return readback


def structural_member(doc: Any, profile_path: str, configuration: str = "Default") -> Dict[str, Any]:
    """沿草图线段放结构构件。先选中线段，再调不需要线段数组的旧接口。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_structural_member",
        "api": "IFeatureManager.InsertStructuralWeldment",
        "status": "unverified", "detail": {"profile": profile_path}, "checks": {},
    }
    if not profile_path:
        from ..weldment_library import default_profile
        found = default_profile()
        profile_path = found["path"] if found else ""
        out["detail"]["profile"] = profile_path
        out["detail"]["standard"] = found["standard"] if found else ""
    if not profile_path or not os.path.isfile(profile_path):
        out["detail"]["error"] = "轮廓文件不存在。可设 NSA_WELDMENT_PROFILES，或安装 SolidWorks 焊件轮廓库"
        out["checks"] = {"profile_exists": False}
        return out
    before_n = count_features(doc)
    before = {str(val(feat, "GetTypeName2")) for feat in iter_features(doc)}
    segments = _sketch_segments(doc)
    if not segments:
        out["detail"]["error"] = "需要一条已经画好的草图线段"
        out["checks"] = {"profile_exists": True, "has_segments": False}
        return out
    try:
        doc.ClearSelection2(True)
        for index, segment in enumerate(segments):
            segment.Select4(index > 0, none_dispatch())
        _sw, md = com_doc()
        md.FeatureManager.InsertStructuralWeldment(profile_path, 0, 0.0)
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["checks"] = {"profile_exists": True, "has_segments": True, "feature_added": False}
        return out
    requested = "" if configuration in ("", "Default") else configuration
    config_error = ""
    readback = ""
    if requested:
        try:
            readback = _set_configuration(doc, requested, before)
        except Exception as exc:  # noqa: BLE001
            config_error = "%s: %s" % (type(exc).__name__, exc)
    new_types = _new_types(doc, before)
    from .features import _volume_mm3
    volume = _volume_mm3(doc)
    member = any(_member_type(name) for name in new_types)
    checks = {
        "profile_exists": True,
        "has_segments": True,
        "feature_added": count_features(doc) > before_n,
        "type_matches": member,
        "has_volume": volume is not None and volume > 1.0,
    }
    if requested:
        checks["configuration"] = readback == requested and not config_error
    out["checks"] = checks
    out["detail"].update({
        "new_types": new_types,
        "segments": len(segments),
        "volume_mm3": volume,
        "configuration_requested": requested or "Default",
        "configuration_readback": readback,
        "configuration_error": config_error,
    })
    out["ok"] = all(checks.values())
    out["status"] = "verified" if out["ok"] else "unverified"
    return out


def profile_configurations(app: Any, path: str) -> List[str]:
    """打开轮廓文件，读配置名，然后关掉。空列表表示没打开。"""
    import pythoncom
    import win32com.client
    from ..core.com import pyw
    errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = app.OpenDoc6(path, 1, 3, "", errors, warnings)
    if doc is None:
        return []
    wrapped = pyw().Dispatch(doc)
    names = [str(name) for name in list(val(wrapped, "GetConfigurationNames") or [])]
    app.CloseDoc(str(val(wrapped, "GetTitle") or ""))
    return names


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
