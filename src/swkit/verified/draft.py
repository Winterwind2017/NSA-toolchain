"""swkit.verified.draft —— 拔模分析的**读取侧**（需要已存在的分型线特征）

## 结论演进（别重复踩）

1. 一开始以为"拔模分析没有可读判据" —— **错**。
2. `IPartingLineFeatureData` 上有硬判据：
   `DraftAnalysis(Angle)` + `GetFacesByTypeCount(Type)`（0 正 / 1 负 / 2 无拔模 / 3 跨面）。
3. 但**入口拿不到**：`CreateDefinition` 的 `swFm`(132) 与 `swFeatureNameID`(8) 里
   都没有分型线类型；`InsertMoldPartingLine(False/True)` 恒 **None**
   （无论选 4 条任意边还是顶面闭合环）；`InsertMoldPartingSurface(8 参)` 能建出
   「分型面1」，但那是**分型面**不是分型线，且它返回的对象没有 `GetDefinition`。
4. `IModelDoc2.MoldDraftAnalysis(Angle, Options, Colors, Shows)`（void，只着色）
   在 3 种 Colors 格式 × Shows 0/1/4 下恒 False，面颜色也无变化。

## 因此本模块的做法

**不创建**分型线，只读取**已存在**的分型线特征：

    feat = 按名字/类型找到分型线特征
    data = feat.GetDefinition().QueryInterface(IPartingLineFeatureData)
    data.DraftAnalysis(angle)
    counts = {t: data.GetFacesByTypeCount(t) for t in (0,1,2,3)}

这样只要有人（手工或在有模具上下文的模型里）建过一次分型线，拔模分析就能自动化，
判据也不再是"返回 True 就算过"。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import comtypes_bundle, val

__all__ = ["find_parting_line", "analyze", "FACE_TYPE_NAMES"]

FACE_TYPE_NAMES = {0: "正拔模", 1: "负拔模", 2: "无拔模", 3: "跨面"}


def _features(doc: Any) -> List[Any]:
    out, feat = [], getattr(doc, "FirstFeature", None)
    while feat is not None:
        out.append(feat)
        try:
            feat = feat.GetNextFeature()
        except Exception:                            # noqa: BLE001
            break
    return out


def find_parting_line(doc: Any, name: Optional[str] = None) -> Optional[Any]:
    """在特征树里找分型线特征（按类型名或给定名字）。"""
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

    判据：四个类型的面数都能读到（整数 ≥ 0），且**正/负/无拔模三者之和 > 0**
    —— 全 0 说明分析没真正执行。
    """
    out: Dict[str, Any] = {"ok": False, "tool": "sw_analyze_draft",
                           "api": "IPartingLineFeatureData.DraftAnalysis + GetFacesByTypeCount",
                           "detail": {}, "checks": {}}
    import math

    feat = find_parting_line(doc, name)
    if feat is None:
        out["detail"]["error"] = "特征树里没有分型线特征（需先手工建一个）"
        out["detail"]["features"] = [
            "%s / %s" % (val(f, "GetTypeName2"), val(f, "Name"))
            for f in _features(doc)][-8:]
        return out
    out["detail"].update({"feature": val(feat, "Name"),
                          "feature_type": val(feat, "GetTypeName2"),
                          "angle_deg": angle_deg})
    try:
        defn = feat.GetDefinition()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "GetDefinition 失败：%s: %s" % (type(exc).__name__, exc)
        return out
    if defn is None:
        out["detail"]["error"] = "GetDefinition 返回 None"
        return out
    mod, _ = comtypes_bundle()
    try:
        pl = defn.QueryInterface(mod.IPartingLineFeatureData)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "不是 IPartingLineFeatureData：%s" % (str(exc)[:80],)
        return out
    try:
        out["detail"]["draft_analysis_returned"] = pl.DraftAnalysis(math.radians(float(angle_deg)))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "DraftAnalysis 失败：%s: %s" % (type(exc).__name__, exc)
        return out
    counts: Dict[int, Any] = {}
    for t in (0, 1, 2, 3):
        try:
            counts[t] = pl.GetFacesByTypeCount(t)
        except Exception as exc:                    # noqa: BLE001
            counts[t] = "ERR:%s" % (str(exc)[:30],)
    out["detail"]["faces_by_type"] = {FACE_TYPE_NAMES.get(k, str(k)): v
                                      for k, v in counts.items()}
    numeric = all(isinstance(v, int) and v >= 0 for v in counts.values())
    total = sum(v for v in counts.values() if isinstance(v, int))
    out["checks"] = {"counts_readable": numeric, "has_drafted_faces": total > 0}
    out["ok"] = all(out["checks"].values())
    return out
