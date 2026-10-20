"""swkit.verified.bodies —— 实体级操作（缩放/删除）

判据全是**几何量**：

| 工具 | 判据 |
|---|---|
| `scale_body` | 包围盒尺寸 × 倍数（实测 40×25×20 → 80×50×40） |
| `delete_body` | 实体数 **2→1** |

实测要点：
* `IBody2.Select2(False, 0)` 在本机**选不中**；要在实体包围盒中心上
  `SelectByID2("", "SOLIDBODY", x, y, z)`。
* `InsertScale` **必须先选中实体**——不选也能调用、不报错，但几何不变（假成功）。
* `InsertMoveCopyBody2` 在三种参数解释下都无位移（dx=0）→ 未达可用。
* 两次相交拉伸会被自动合并成一个体（gap=0 → count=1），所以"两个体重叠再布尔加"
  这个夹具造不出来 → `combine_bodies` 未达可用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, val
from ._common import wrap

__all__ = ["scale_body", "delete_body", "body_stats", "select_body"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _bodies(doc: Any) -> List[Any]:
    try:
        return [wrap(b) for b in (doc.GetBodies2(0, True) or [])]
    except Exception:
        return []


def _box_mm(body: Any) -> Optional[List[float]]:
    try:
        box = val(body, "GetBodyBox")
        return [round(float(v) * 1000.0, 4) for v in box[:6]]
    except Exception:
        return None


def _volume_mm3(doc: Any) -> Optional[float]:
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        mp = md.Extension.CreateMassProperty()
        v = mp.Volume
        return round(float(v) * 1e9, 3) if v is not None else None
    except Exception:
        return None


def body_stats(doc: Any) -> Dict[str, Any]:
    """实体数与包围盒快照。"""
    bodies = _bodies(doc)
    return {"count": len(bodies),
            "boxes_mm": [_box_mm(b) for b in bodies],
            "volume_mm3": _volume_mm3(doc)}


def select_body(doc: Any, index: int = 0, append: bool = False) -> bool:
    """选中第 index 个实体（按包围盒中心点选）。"""
    bodies = _bodies(doc)
    if index >= len(bodies):
        return False
    box = _box_mm(bodies[index])
    if not box:
        return False
    cx = (box[0] + box[3]) / 2.0 / 1000.0
    cy = (box[1] + box[4]) / 2.0 / 1000.0
    cz = (box[2] + box[5]) / 2.0 / 1000.0
    try:
        if not append:
            doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2("", "SOLIDBODY", cx, cy, cz, bool(append),
                                       0, none_dispatch(), 0)
        return bool(ok)
    except Exception:
        return False


def scale_body(doc: Any, factor: float = 2.0) -> Dict[str, Any]:
    """整体缩放。判据：包围盒尺寸 × 倍数。"""
    out = _result("sw_scale_body", "IModelDoc2.InsertScale(5 参)")
    before = body_stats(doc)
    out["detail"].update({"factor": factor, "before": before})
    try:
        # 必须先选中实体：不选也能调用、不报错，但几何不变（假成功）
        out["detail"]["selected"] = select_body(doc, 0)
        doc.InsertScale(float(factor), float(factor), float(factor), True, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = body_stats(doc)
    out["detail"]["after"] = after

    def size(box):
        return None if not box else [round(box[3] - box[0], 4),
                                    round(box[4] - box[1], 4),
                                    round(box[5] - box[2], 4)]

    b0 = size(before["boxes_mm"][0]) if before["boxes_mm"] else None
    b1 = size(after["boxes_mm"][0]) if after["boxes_mm"] else None
    out["detail"].update({"size_before_mm": b0, "size_after_mm": b1})
    ok = bool(b0 and b1) and all(abs(b1[i] - b0[i] * factor) < 0.05 for i in range(3))
    out["checks"] = {"bbox_scaled": ok}
    out["ok"] = out["checks"]["bbox_scaled"]
    return out


def delete_body(doc: Any, body_index: int = 0) -> Dict[str, Any]:
    """删除实体。判据：实体数 -1。"""
    out = _result("sw_delete_body", "IFeatureManager.InsertDeleteBody")
    before = len(_bodies(doc))
    out["detail"]["bodies_before"] = before
    if not select_body(doc, body_index):
        out["detail"]["error"] = "选不中实体"
        return out
    try:
        fm = doc.FeatureManager
        try:
            feat = fm.InsertDeleteBody()
        except Exception:
            feat = fm.InsertDeleteBody2(True)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = len(_bodies(doc))
    out["detail"].update({"bodies_after": after,
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"body_removed": after == before - 1}
    out["ok"] = out["checks"]["body_removed"]
    return out
