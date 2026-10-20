"""swkit.verified.draft —— 拔模分析（读取侧 + 正确的调用顺序）

## 结论演进（别重复踩）

1. 一开始以为"拔模分析没有可读判据" —— **错**。
2. `IPartingLineFeatureData` 上有硬判据：`DraftAnalysis(Angle)` +
   `GetFacesByTypeCount(Type)`（0 正 / 1 负 / 2 无拔模 / 3 跨面）。
3. 但**分型线无法用 API 创建**：`CreateDefinition` 的 `swFm`(132) 与
   `swFeatureNameID`(8) 里都没有该类型；`InsertMoldPartingLine(False/True)` 恒 None
   （选 4 条任意边、选顶面闭合环都一样）。
4. `IModelDoc2.MoldDraftAnalysis(Angle, Options, Colors, Shows)`（void，只着色）
   在 3 种 Colors × Shows 0/1/4 下恒 False，面颜色也无变化。

## 正确调用顺序（实测，缺一不可）

    feat  = 特征树里的 MoldPartingLine 特征              # 需人工建好
    data  = feat.GetDefinition → QI IPartingLineFeatureData
    data.AccessSelections(md, None)                       # ← 少了这句 DraftAnalysis 恒 False
    data.DraftAnalysis(radians(angle))                    # → True
    counts = [data.GetFacesByTypeCount(t) for t in 0..3]   # → [1, 1, 4, 0]，合计 = 面数
    data.ReleaseSelectionAccess()

三个坑：
* `GetDefinition` 在 pywin32 下是**属性**（调用报"找不到成员"）
* pywin32 的 CDispatch **没有 QueryInterface**，必须换 comtypes 侧重新定位特征
* `GetFacesByTypeCount` 必须**带类型参数调用**（`val()` 只读属性，会把方法本身返回）
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from ..core.com import val

__all__ = ["find_parting_line", "analyze", "FACE_TYPE_NAMES"]

FACE_TYPE_NAMES = {0: "正拔模", 1: "负拔模", 2: "无拔模", 3: "跨面"}


def _features(doc: Any) -> List[Any]:
    """复用已验证的遍历（`FirstFeature` 在 pywin32 是属性、comtypes 是方法）。"""
    from ._common import iter_features
    return list(iter_features(doc))


def find_parting_line(doc: Any, name: Optional[str] = None) -> Optional[Any]:
    """在特征树里找分型线特征（类型 `MoldPartingLine`，或按给定名字）。"""
    for feat in _features(doc):
        try:
            kind = str(val(feat, "GetTypeName2"))
            fname = str(val(feat, "Name"))
        except Exception:                            # noqa: BLE001
            continue
        if name:
            if fname == name:
                return feat
            continue
        if kind in ("MoldPartingLine", "PartingLine") or "分型线" in fname:
            return feat
    return None


def analyze(doc: Any, angle_deg: float = 1.0,
            name: Optional[str] = None) -> Dict[str, Any]:
    """对已有分型线跑拔模分析，返回各类型面数。

    判据：`DraftAnalysis` 返回 True、四个计数可读、且合计 = 零件面数。
    """
    out: Dict[str, Any] = {"ok": False, "tool": "sw_analyze_draft",
                           "api": "IPartingLineFeatureData.DraftAnalysis + GetFacesByTypeCount",
                           "detail": {}, "checks": {}}
    feat = find_parting_line(doc, name)
    if feat is None:
        out["detail"]["error"] = "特征树里没有分型线特征（需先手工建一个）"
        out["detail"]["features"] = [
            "%s / %s" % (val(f, "GetTypeName2"), val(f, "Name"))
            for f in _features(doc)][-8:]
        return out
    target_name = str(val(feat, "Name"))
    out["detail"].update({"feature": target_name,
                          "feature_type": val(feat, "GetTypeName2"),
                          "angle_deg": angle_deg})

    from ._common import com_doc, bodies, faces_of
    try:
        sw, md = com_doc()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "取 comtypes 文档失败：%s: %s" % (type(exc).__name__, exc)
        return out

    data = None
    try:
        cand = val(md, "FirstFeature")
        guard = 0
        while cand is not None and guard < 2000:
            guard += 1
            if str(val(cand, "Name")) == target_name:
                definition = val(cand, "GetDefinition")
                if definition is not None:
                    data = definition.QueryInterface(sw.IPartingLineFeatureData)
                break
            cand = val(cand, "GetNextFeature")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "取 IPartingLineFeatureData 失败：%s: %s" % (
            type(exc).__name__, exc)
        return out
    if data is None:
        out["detail"]["error"] = "该特征的定义不是 IPartingLineFeatureData"
        return out

    accessed = False
    try:
        accessed = bool(data.AccessSelections(md, None))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["access_error"] = str(exc)[:100]
    try:
        returned = data.DraftAnalysis(math.radians(float(angle_deg)))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "DraftAnalysis 失败：%s: %s" % (type(exc).__name__, exc)
        return out
    counts: Dict[int, Any] = {}
    for t in (0, 1, 2, 3):
        try:
            counts[t] = data.GetFacesByTypeCount(t)
        except Exception as exc:                    # noqa: BLE001
            counts[t] = "ERR:%s" % (str(exc)[:30],)
    try:
        if accessed:
            data.ReleaseSelectionAccess()
    except Exception:                               # noqa: BLE001
        pass

    # 拔模分析只统计**实体**面；分型面等曲面体的面不参与（实测 12 vs 6 就是差在这里）
    faces_total = sum(len(faces_of(b)) for b in bodies(doc, 0))
    total = sum(v for v in counts.values() if isinstance(v, int))
    out["detail"].update({
        "access_selections": accessed,
        "draft_analysis_returned": returned,
        "faces_by_type": {FACE_TYPE_NAMES[k]: v for k, v in counts.items()},
        "faces_total": faces_total,
        "faces_sum": total,
    })
    numeric = all(isinstance(v, int) and v >= 0 for v in counts.values())
    out["checks"] = {
        "analysis_performed": returned is True,
        "counts_readable": numeric,
        "sum_matches_solid_faces": faces_total == total,
    }
    out["ok"] = all(out["checks"].values())
    return out
