"""筋特征。参数顺序来自本机 sldworks.tlb 的 InsertRib，不看调用返回值。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..core.com import val
from ._common import com_doc, count_features, iter_features

__all__ = ["insert_rib", "judge_rib"]


def judge_rib(features_before: int, features_after: int,
              volume_before: Optional[float], volume_after: Optional[float],
              new_types: Iterable[str]) -> Dict[str, bool]:
    types = [str(name).lower() for name in new_types]
    volume_up = (
        volume_before is not None and volume_after is not None
        and volume_after > volume_before + 0.1
    )
    return {
        "feature_added": features_after == features_before + 1,
        "type_is_rib": any("rib" in name for name in types),
        "volume_up": volume_up,
    }


def _types(doc: Any) -> list:
    return [str(val(feat, "GetTypeName2")) for feat in iter_features(doc)]


def insert_rib(doc: Any, thickness_mm: float = 3.0, two_sided: bool = True,
               reference_edge: int = 0, reverse_thickness: bool = False,
               reverse_material: bool = False) -> Dict[str, Any]:
    """在当前草图上加筋。厚度单位是毫米，传给 API 前换成米。"""
    out: Dict[str, Any] = {
        "ok": False,
        "tool": "sw_rib",
        "api": "IFeatureManager.InsertRib",
        "status": "unverified",
        "detail": {},
        "checks": {},
    }
    if thickness_mm <= 0:
        out["detail"]["error"] = "厚度必须大于 0"
        return out
    before_n = count_features(doc)
    before_types = set(_types(doc))
    from .features import _volume_mm3
    from .sketch_ops import _select_all_segments
    volume_before = _volume_mm3(doc)
    selected = _select_all_segments(doc)
    try:
        _sw, md = com_doc()
        returned = md.FeatureManager.InsertRib(
            bool(two_sided),
            bool(reverse_thickness),
            float(thickness_mm) / 1000.0,
            int(reference_edge),
            bool(reverse_material),
            False,
            False,
            0.0,
            True,
            False,
        )
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["detail"]["segments_selected"] = selected
        return out
    out["detail"]["returned_type"] = type(returned).__name__
    out["detail"]["segments_selected"] = selected
    after_types = _types(doc)
    new_types = [name for name in after_types if name not in before_types]
    volume_after = _volume_mm3(doc)
    checks = judge_rib(before_n, count_features(doc), volume_before, volume_after, new_types)
    out["checks"] = checks
    out["detail"].update({
        "thickness_mm": thickness_mm,
        "new_types": new_types,
        "volume_before_mm3": volume_before,
        "volume_after_mm3": volume_after,
    })
    out["ok"] = all(checks.values())
    return out
