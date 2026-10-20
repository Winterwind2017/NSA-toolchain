"""swkit.verified.analysis —— 装配干涉检查（+ 两项"无判据"的如实记录）

| 工具 | 判据 |
|---|---|
| `interference_check` | 两件分开放 120 mm → 干涉 **0**；重叠 20 mm → **1**；完全重合 → **1** |

## 为什么只有干涉这一项

* **几何检查**：`sldworks.tlb` 里与此相关的只有 `IModelDoc2.DebugCheckBody()` /
  `DebugCheckIgesGeom()`，**没有** `CheckGeometry` 之类的公开方法 → 无 API。
* **拔模分析**：`IModelDoc2.MoldDraftAnalysis(Angle, Options, Colors, Shows)` 是
  **Sub（void）**，只把面着色，TLB 里也没有 `GetDraftAnalysisFaces` 之类读回方法
  → 拿不到计数，只有"没报错"。按本仓库规矩（不看返回值、只读数）**不列为已验证**。

## 使用要点（实测）

* 干涉要用 `IAssemblyDoc.InterferenceDetectionManager`，读 `GetInterferenceCount()`
  或 `GetInterferences()`（返回数组）。
* 组件位置单位是 **mm**：`insert_component(..., x_mm=120)` 才是 120 mm。
  传 `0.12`（当米的习惯）会让零件几乎叠在原点（实测偏 0.12 mm），
  此时"干涉数"当然不对——这是我自己在端到端测量里踩到的。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import val

__all__ = ["interference_check", "geometry_check_available",
           "draft_analysis_available", "UNSUPPORTED_REASONS"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


UNSUPPORTED_REASONS = {
    "check_geometry": "sldworks.tlb 无 CheckGeometry 类方法（只有 IModelDoc2.DebugCheckBody）",
    "draft_analysis": "MoldDraftAnalysis 是 Sub(void)，只着色；TLB 无读回面集的方法",
}


def geometry_check_available() -> bool:
    return False


def draft_analysis_available() -> bool:
    return False


def _interferences(mgr: Any) -> List[Any]:
    try:
        arr = val(mgr, "GetInterferences")
    except Exception:
        return []
    try:
        return list(arr or [])
    except TypeError:
        return []


def interference_check(asm_doc: Any, expected: Optional[int] = None,
                       treat_coincidence: bool = False) -> Dict[str, Any]:
    """装配干涉检查。

    * `expected` 给定时，判据 = 实测干涉数 == 期望值
    * 不给时，判据 = 干涉数可读（≥0）
    """
    out = _result("sw_check_interference",
                  "IAssemblyDoc.InterferenceDetectionManager.GetInterferenceCount")
    try:
        mgr = asm_doc.InterferenceDetectionManager
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if mgr is None:
        out["detail"]["error"] = "取不到 InterferenceDetectionManager（需装配文档）"
        return out
    try:
        # 这两个开关会改变判定口径，显式设定并回读，避免"沿用上次会话设置"
        mgr.TreatCoincidenceAsInterference = bool(treat_coincidence)
        mgr.IncludeMultibodyPartInterferences = True
        out["detail"]["treat_coincidence"] = bool(
            val(mgr, "TreatCoincidenceAsInterference"))
        out["detail"]["include_multibody"] = bool(
            val(mgr, "IncludeMultibodyPartInterferences"))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["settings_error"] = str(exc)[:80]
    count = val(mgr, "GetInterferenceCount")
    items = _interferences(mgr)
    out["detail"].update({"interference_count": count,
                          "array_length": len(items),
                          "expected": expected})
    checks = {"count_readable": isinstance(count, int) and count >= 0,
              "array_matches_count": (not isinstance(count, int)) or len(items) == count}
    if expected is not None:
        checks["matches_expected"] = count == expected
    out["checks"] = checks
    out["ok"] = all(checks.values())
    return out
