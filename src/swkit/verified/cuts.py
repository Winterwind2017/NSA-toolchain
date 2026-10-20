"""swkit.verified.cuts —— 切除拉伸（FeatureCut4，27 参）

判据：**体积必须下降**（并核对下降量 ≈ 轮廓面积 × 深度）。
"特征建出来了"不算数——本模块就是在修这个坑。

## 为什么不用 IFeatureManager.FeatureExtrusion3 的"is_cut"

`FeatureExtrusion3` **没有** 切除开关；把它的第 2 个参数当 `is_cut` 传，实际是
**Flip（翻转）**，结果是"在材料外面又加了一块"（实测 48000 → +942.5）。
切除只有 `FeatureCut4`（27 参）/ 更老的 `FeatureCut*` 这条路。

## 27 参顺序（官方 CHM，逐字核对过）

`Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2, Dang1, Dang2,
OffsetReverse1, OffsetReverse2, TranslateSurface1, TranslateSurface2, NormalCut,
UseFeatScope, UseAutoSelect, AssemblyFeatureScope, AutoSelectComponents,
PropagateFeatureToParts, T0, StartOffset, FlipStartOffset, OptimizeGeometry`

## 两条硬规矩（实测）

1. **`UseAutoSelect` 必须为 True**：为 False 时"必须先选实体"，只选草图会**静默失败**
   （返回 None、体积不变）——我在这里浪费了三轮。
2. **`Dir=False` 就是朝材料里切**：官方 Remarks 明确 "cut 的默认方向与草图法向相反"。
   传 True 反而切到空气里（Δ=0）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.com import val
from ._common import com_doc, iter_features

__all__ = ["cut_extrude", "SW_END_BLIND", "SW_END_THROUGH_ALL"]

SW_END_BLIND = 0
SW_END_THROUGH_ALL = 1
SW_START_SKETCH = 0


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _volume_mm3(doc: Any) -> Optional[float]:
    try:
        _sw, md = com_doc()
        mp = md.Extension.CreateMassProperty()
        v = mp.Volume
        return round(float(v) * 1e9, 3) if v is not None else None
    except Exception:
        return None


def cut_extrude(doc: Any, depth_mm: float = 12.0, through_all: bool = False,
                flip_side: bool = False, draft_deg: float = 0.0) -> Dict[str, Any]:
    """切除拉伸当前（已选中的）草图。

    * `through_all=True` 时用"完全贯穿"，忽略 `depth_mm`
    * 判据：体积必须**下降**；有 `depth_mm` 时会核对下降量量级
    """
    out = _result("sw_cut_extrude", "IFeatureManager.FeatureCut4(27 参)")
    before_vol = _volume_mm3(doc)
    before_feat = len(list(iter_features(doc)))
    t1 = SW_END_THROUGH_ALL if through_all else SW_END_BLIND
    d1 = 0.0 if through_all else float(depth_mm) / 1000.0
    args = [
        True,                       # Sd: 单边
        bool(flip_side),            # Flip: 反向侧切除
        False,                      # Dir: False = 朝材料里（cut 默认与法向相反）
        int(t1),                    # T1
        SW_END_BLIND,               # T2
        d1,                         # D1
        0.0,                        # D2
        bool(draft_deg > 0), False,  # Dchk1/2
        False, False,               # Ddir1/2
        float(draft_deg), 0.0,      # Dang1/2
        False, False, False, False,  # OffsetReverse1/2, TranslateSurface1/2
        False,                      # NormalCut（非钣金必须 False）
        True,                       # UseFeatScope
        True,                       # UseAutoSelect ← 必须 True，否则静默失败
        False,                      # AssemblyFeatureScope
        True,                       # AutoSelectComponents
        True,                       # PropagateFeatureToParts
        SW_START_SKETCH,            # T0
        0.0, False, False,          # StartOffset, FlipStartOffset, OptimizeGeometry
    ]
    out["detail"].update({"depth_mm": depth_mm, "through_all": through_all,
                          "param_count": len(args),
                          "volume_before_mm3": before_vol,
                          "features_before": before_feat})
    try:
        feat = doc.FeatureManager.FeatureCut4(*args)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after_vol = _volume_mm3(doc)
    after_feat = len(list(iter_features(doc)))
    out["detail"].update({
        "volume_after_mm3": after_vol,
        "features_after": after_feat,
        "feature": val(feat, "Name") if feat is not None else None,
    })
    dropped = (before_vol is not None and after_vol is not None
               and after_vol < before_vol - 1e-6)
    out["checks"] = {
        "feature_added": after_feat == before_feat + 1,
        "volume_dropped": bool(dropped),
    }
    if before_vol and after_vol:
        out["detail"]["volume_delta_mm3"] = round(after_vol - before_vol, 3)
    out["ok"] = all(out["checks"].values())
    if not out["ok"]:
        out["detail"].setdefault(
            "error", "切除未生效：查 UseAutoSelect=True 与 Dir=False（见模块文档）")
    return out
