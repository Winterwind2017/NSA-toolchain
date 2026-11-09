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

__all__ = ["scale_body", "delete_body", "move_body", "combine_bodies",
           "body_stats", "select_body"]


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


def move_body(doc: Any, dx_mm: float = 0.0, dy_mm: float = 0.0, dz_mm: float = 0.0,
              copy: bool = False, copies: int = 1) -> Dict[str, Any]:
    """平移（或复制）实体：InsertMoveCopyBody2。

    实测要点（SW 2025 SP4.1）：
    * TransX/Y/Z 是**字面米制位移**，不是方向分量——传 1.0 就移动 1000 mm；
      TransDist 在平移模式下**被忽略**（传 0.02 与 0 结果相同）
    * 实体必须用 SelectByID2("", "SOLIDBODY", x, y, z, ..., mark=1, ...) 选中，
      mark=0 会选不中；坐标单位是**米**
    * copy=True, copies=2 → 实体 1→**3**

    判据：包围盒位移 = 请求位移（±0.5 mm）；复制时实体数 +copies。
    """
    out = _result("sw_move_body", "IFeatureManager.InsertMoveCopyBody2(12 参)")
    before = _bodies(doc)
    if not before:
        out["detail"]["error"] = "没有实体"
        return out
    box0 = _box_mm(before[0])
    out["detail"].update({"dx_mm": dx_mm, "dy_mm": dy_mm, "dz_mm": dz_mm,
                          "copy": bool(copy), "copies": int(copies),
                          "bodies_before": len(before),
                          "box_before_mm": box0})
    selected = 0
    for b in before:
        box = _box_mm(b)
        if not box or len(box) < 6:
            continue
        cx = (box[0] + box[3]) / 2.0 / 1000.0
        cy = (box[1] + box[4]) / 2.0 / 1000.0
        cz = (box[2] + box[5]) / 2.0 / 1000.0
        try:
            if doc.Extension.SelectByID2("", "SOLIDBODY", cx, cy, cz, selected > 0, 1,
                                         none_dispatch(), 0):
                selected += 1
        except Exception:                          # noqa: BLE001
            continue
    out["detail"]["selected"] = selected
    if not selected:
        out["detail"]["error"] = "实体选不中（需要 SOLIDBODY + mark 1）"
        return out
    try:
        feat = doc.FeatureManager.InsertMoveCopyBody2(
            float(dx_mm) / 1000.0, float(dy_mm) / 1000.0, float(dz_mm) / 1000.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, bool(copy), int(copies))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _bodies(doc)
    box1 = _box_mm(after[0]) if after else None
    out["detail"].update({"bodies_after": len(after), "box_after_mm": box1,
                          "feature": None if feat is None else str(val(feat, "Name"))})
    if box0 and box1 and len(box0) >= 6 and len(box1) >= 6:
        got = [round(box1[i] - box0[i], 3) for i in range(3)]
        want = [round(float(dx_mm), 3), round(float(dy_mm), 3), round(float(dz_mm), 3)]
        out["detail"]["delta_mm"] = got
        out["detail"]["delta_expected_mm"] = want
        moved = all(abs(got[i] - want[i]) <= 0.5 for i in range(3))
    else:
        moved = False
    if copy:
        # 复制模式下**原件不动**，只有副本平移 → 不能拿第一个体的位移当判据
        out["checks"] = {"bodies_increased": len(after) > len(before)}
    else:
        out["checks"] = {"moved_as_requested": bool(moved)}
    out["ok"] = all(out["checks"].values())
    return out


# `swBodyOperationType_e`（注意不是 swCombineBodiesOperationType_e）
BODY_OP_ADD = 15903
BODY_OP_CUT = 15902
BODY_OP_INTERSECT = 15901
_BODY_OPS = {"add": BODY_OP_ADD, "cut": BODY_OP_CUT, "intersect": BODY_OP_INTERSECT}


def combine_bodies(doc: Any, operation: str = "add") -> Dict[str, Any]:
    """组合实体：`IFeatureManager.InsertCombineFeature`。

    实测要点（SW 2025 SP4.1）：

    * `OperationType` 取 **`swBodyOperationType_e`**（SWBODYADD=15903），
      不是 `swCombineBodiesOperationAdd=0` —— 传 0 不报错但**不生成特征**
    * `SWBODYADD` 时 `MainBody` 必须传 **`none_dispatch()`**（空 IDispatch）；
      传 `None` / `0` 都报"类型不匹配"
    * `ToolVar` 要 `VARIANT(VT_ARRAY|VT_DISPATCH, [body, body, ...])`

    实测：两块 40×25×10 重叠 20 mm → 实体 2→**1**、
    体积 20000→**15000**（= 10000+10000−5000，并集解析值）
    """
    out = _result("sw_combine_bodies", "IFeatureManager.InsertCombineFeature(3 参)")
    import pythoncom
    from win32com.client import VARIANT

    op = _BODY_OPS.get(str(operation).lower())
    if op is None:
        out["detail"]["error"] = "operation 只能是 add/cut/intersect"
        return out
    bodies = _bodies(doc)
    out["detail"].update({"operation": operation, "operation_type": op,
                          "bodies_before": len(bodies)})
    if len(bodies) < 2:
        out["detail"]["error"] = "至少需要 2 个实体（可先用 move_body(copy=True) 造第二个）"
        return out
    vols = []
    for b in bodies:
        try:
            vols.append(round(float(b.GetMassProperties(0)[3]) * 1e9, 3))
        except Exception:                           # noqa: BLE001
            vols.append(None)
    out["detail"]["body_volumes_mm3"] = vols
    arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(bodies))
    try:
        feat = doc.FeatureManager.InsertCombineFeature(op, none_dispatch(), arr)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _bodies(doc)
    out["detail"].update({"bodies_after": len(after),
                          "feature": None if feat is None else str(val(feat, "Name"))})
    checked_vol = None
    if after:
        try:
            checked_vol = round(float(after[0].GetMassProperties(0)[3]) * 1e9, 3)
        except Exception:                           # noqa: BLE001
            checked_vol = None
    out["detail"]["volume_after_mm3"] = checked_vol
    checks = {"feature_created": feat is not None,
              "bodies_decreased": len(after) < len(bodies)}
    known = [v for v in vols if v]
    if checked_vol and known:
        total = round(sum(known), 3)
        checks["volume_within_bounds"] = (max(known) - 1.0 <= checked_vol <= total + 1.0)
        out["detail"]["volume_sum_before_mm3"] = total
    out["checks"] = checks
    out["ok"] = all(checks.values())
    return out
