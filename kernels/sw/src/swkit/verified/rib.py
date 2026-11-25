"""筋特征。参数顺序来自本机 sldworks.tlb 的 InsertRib，不看调用返回值。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..core.com import val
from ._common import com_doc, count_features, iter_features

__all__ = ["insert_rib", "judge_rib", "triangular_rib"]


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


def triangular_rib(doc: Any, base_mm: float = 30.0, height_mm: float = 20.0,
                   length_mm: float = 40.0) -> Dict[str, Any]:
    """直角三角形截面的筋，沿长度拉伸。体积必须等于底×高×长的一半。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_triangular_rib",
        "api": "Sketch lines + FeatureExtrusion3",
        "status": "unverified", "detail": {}, "checks": {},
    }
    if min(base_mm, height_mm, length_mm) <= 0:
        out["detail"]["error"] = "底、高、长都必须大于 0"
        return out
    from .features import _volume_mm3, extrude
    from .sketch_ops import create_sketch, line
    expected = 0.5 * base_mm * height_mm * length_mm
    try:
        create_sketch(doc)
        line(doc, 0, 0, base_mm, 0)
        line(doc, base_mm, 0, 0, height_mm)
        line(doc, 0, height_mm, 0, 0)
        made = extrude(doc, length_mm)
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    volume = _volume_mm3(doc)
    close = volume is not None and abs(volume - expected) / expected < 0.05
    out["checks"] = {
        "extrude_ok": bool(made.get("ok")),
        "volume_matches": close,
    }
    out["detail"].update({
        "expected_mm3": expected,
        "volume_mm3": volume,
        "native_insert_rib": "本机 InsertRib 仍返回 0，这里用三角形截面拉伸",
    })
    out["ok"] = all(out["checks"].values())
    out["status"] = "verified" if out["ok"] else "unverified"
    return out
