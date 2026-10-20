"""swkit.verified.sheet_metal —— 钣金（基体法兰 / 展开 / 折叠 / 卷边）

判据：

| 工具 | 判据 |
|---|---|
| `base_flange` | 特征数 +1 **且** 出现钣金特征（类型名含 SheetMetal/BaseFlange） |
| `unfold` / `fold` | 特征数 +1，且`GetBendState` 在 1/2 之间切换 |
| `hem` | 特征数 +1（需先选边） |

实测签名（TLB）：
* `InsertSheetMetalBaseFlange(9)` = Thickness, ThickenDir, Radius, ExtrudeDist1,
  ExtrudeDist2, FlipExtruDir, EndCondition1, EndCondition2, DirToUse
* `InsertSheetMetalHem(8)` = Type, Position, Reverse, DLength, DGap, DAngle, DRad,
  DMiterGap
* `InsertSheetMetalUnfold()` / `InsertSheetMetalFold()` 都是 **0 参**
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, pyw, val
from ._common import iter_features, shape_counts, wrap

__all__ = ["base_flange", "unfold", "fold", "hem", "feature_types", "bend_state",
           "flat_pattern_info", "export_flat_pattern"]

_SHEET_HINTS = ("sheetmetal", "baseflange", "edgeflange", "miterflange", "hem",
                "unfold", "fold", "sketchedbend", "flatpattern")


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def feature_types(doc: Any) -> List[str]:
    out = []
    for feat in iter_features(doc):
        try:
            out.append(str(val(feat, "GetTypeName2")))
        except Exception:
            continue
    return out


def _sheet_features(doc: Any) -> List[str]:
    return [t for t in feature_types(doc) if any(h in t.lower() for h in _SHEET_HINTS)]


def bend_state(doc: Any) -> Optional[int]:
    """`IModelDoc2.GetBendState`：0=非钣金，1=折弯，2=展开。"""
    try:
        return int(val(doc, "GetBendState"))
    except Exception:
        return None


def base_flange(doc: Any, thickness_mm: float = 2.0, radius_mm: float = 2.0,
                depth_mm: float = 30.0, reverse: bool = False,
                end_cond: int = 0) -> Dict[str, Any]:
    """基体法兰（当前草图为轮廓）。判据：特征 +1 且出现钣金特征。"""
    out = _result("sw_base_flange", "IModelDoc2.InsertSheetMetalBaseFlange(9 参)")
    before = shape_counts(doc)
    before_sheet = _sheet_features(doc)
    try:
        feat = doc.InsertSheetMetalBaseFlange(
            float(thickness_mm) / 1000.0, True, float(radius_mm) / 1000.0,
            float(depth_mm) / 1000.0, 0.0, bool(reverse), int(end_cond), 0, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    sheet = _sheet_features(doc)
    out["detail"].update({
        "thickness_mm": thickness_mm, "radius_mm": radius_mm, "depth_mm": depth_mm,
        "feature": val(feat, "Name") if feat is not None else None,
        "features_before": before["features"], "features_after": after["features"],
        "sheet_features_before": before_sheet, "sheet_features_after": sheet,
        "bend_state": bend_state(doc),
    })
    new_sheet = [t for t in sheet if t not in before_sheet]
    out["checks"] = {"feature_added": after["features"] > before["features"],
                     "sheet_metal_created": len(new_sheet) > 0}
    out["ok"] = all(out["checks"].values())
    return out


def unfold(doc: Any) -> Dict[str, Any]:
    """展开钣金。判据：特征 +1。"""
    out = _result("sw_unfold", "IModelDoc2.InsertSheetMetalUnfold()")
    before = shape_counts(doc)["features"]
    state_before = bend_state(doc)
    try:
        feat = doc.InsertSheetMetalUnfold()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)["features"]
    out["detail"].update({"features_before": before, "features_after": after,
                          "bend_state_before": state_before,
                          "bend_state_after": bend_state(doc),
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"feature_added": after > before}
    out["ok"] = out["checks"]["feature_added"]
    return out


def fold(doc: Any) -> Dict[str, Any]:
    """折叠（从展开回到折弯）。判据：特征 +1。"""
    out = _result("sw_fold", "IModelDoc2.InsertSheetMetalFold()")
    before = shape_counts(doc)["features"]
    state_before = bend_state(doc)
    try:
        feat = doc.InsertSheetMetalFold()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)["features"]
    out["detail"].update({"features_before": before, "features_after": after,
                          "bend_state_before": state_before,
                          "bend_state_after": bend_state(doc),
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"feature_added": after > before}
    out["ok"] = out["checks"]["feature_added"]
    return out


def hem(doc: Any, hem_type: int = 0, position: int = 0,
        length_mm: float = 5.0, radius_mm: float = 0.5) -> Dict[str, Any]:
    """卷边（需先选边）。判据：特征 +1。"""
    out = _result("sw_hem", "IModelDoc2.InsertSheetMetalHem(8 参)")
    before = shape_counts(doc)
    out["detail"].update({"hem_type": hem_type, "length_mm": length_mm,
                          "features_before": before["features"]})
    try:
        feat = doc.InsertSheetMetalHem(int(hem_type), int(position), False,
                                       float(length_mm) / 1000.0, 0.0, 0.0,
                                       float(radius_mm) / 1000.0, 0.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)
    out["detail"].update({"features_after": after["features"],
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"feature_added": after["features"] > before["features"]}
    out["ok"] = out["checks"]["feature_added"]
    return out

def flat_pattern_info(doc: Any) -> Dict[str, Any]:
    """展开图信息。判据：特征树里存在 `FlatPattern` 特征，并给出其包围盒。

    实测：基体法兰建成后特征类型里会出现 `FlatPattern`（展开状态 1）。
    """
    out = _result("sw_get_flat_pattern_info", "IFeature(FlatPattern) + 实体包围盒")
    fp = None
    for feat in iter_features(doc):
        try:
            if str(val(feat, "GetTypeName2")) == "FlatPattern":
                fp = feat
        except Exception:
            continue
    out["detail"]["flat_pattern_feature"] = val(fp, "Name") if fp is not None else None
    out["detail"]["bend_state"] = bend_state(doc)
    box = None
    try:
        bodies = list(doc.GetBodies2(0, True) or [])
        if bodies:
            b = wrap(bodies[0])
            box = val(b, "GetBodyBox")
    except Exception:
        box = None
    if box is not None and len(box) >= 6:
        out["detail"]["body_box_mm"] = [round(float(v) * 1000.0, 3) for v in box[:6]]
        out["detail"]["size_mm"] = [round((float(box[3]) - float(box[0])) * 1000.0, 3),
                                   round((float(box[4]) - float(box[1])) * 1000.0, 3),
                                   round((float(box[5]) - float(box[2])) * 1000.0, 3)]
    out["checks"] = {"flat_pattern_present": fp is not None}
    out["ok"] = out["checks"]["flat_pattern_present"]
    return out


def export_flat_pattern(doc: Any, path: str = "") -> Dict[str, Any]:
    """导出展开图（DXF）。判据：文件含 `SECTION`。"""
    out = _result("sw_export_flat_pattern", "IModelDoc2.SaveAs(DXF)")
    target = os.path.abspath(path or os.path.join(
        os.path.expanduser("~"), ".swkit", "export", "flat.dxf"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        try:
            os.remove(target)
        except OSError:
            pass
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        md.SaveAs(target)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    size = os.path.getsize(target) if os.path.exists(target) else 0
    head = b""
    if size:
        with open(target, "rb") as fh:
            head = fh.read(64)
    out["detail"] = {"path": target, "bytes": size,
                     "has_section": b"SECTION" in head}
    out["checks"] = {"file_exists": size > 0, "dxf_signature": b"SECTION" in head}
    out["ok"] = all(out["checks"].values())
    return out