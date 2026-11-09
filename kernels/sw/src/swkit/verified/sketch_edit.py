"""swkit.verified.sketch_edit —— 草图编辑（裁剪/延伸/圆角/倒角/转换实体/3D 草图）

判据：

| 工具 | 判据 |
|---|---|
| `trim` | 草图**线段总长**或数量变化（裁剪点附近的线段被切掉） |
| `extend` | 线段总长**增加** |
| `fillet` / `chamfer` | 线段数 **+1**（多出一段圆弧/斜线） |
| `convert_entities` | 线段数 **+1**（模型边被投影进来） |
| `start_3d_sketch` | 活动草图存在且 **3D 标志**成立 |

实测签名（TLB）：
* `SketchTrim(Op, SelEnd, X, Y)` **4 参**（X/Y 是**米**的草图坐标）
* `SketchExtend(X, Y, Z)` **3 参**
* `SketchFillet(Rad)` 1 参、`SketchChamfer(AngleORdist, Dist1, Options)` 3 参
* `SketchUseEdge()` / `Insert3DSketch()` 都是 0 参
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..core.com import val

__all__ = ["trim", "extend", "fillet", "chamfer", "convert_entities",
           "start_3d_sketch", "seg_stats"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def seg_stats(doc: Any) -> Tuple[int, float]:
    """活动草图（线段数, 总长 mm）。没有活动草图返回 (-1, 0.0)。"""
    try:
        sk = doc.SketchManager.ActiveSketch
    except Exception:
        return (-1, 0.0)
    if sk is None:
        return (-1, 0.0)
    segs = val(sk, "GetSketchSegments")
    try:
        items = list(segs or [])
    except TypeError:
        return (-1, 0.0)
    total = 0.0
    for seg in items:
        try:
            total += float(val(seg, "GetLength")) * 1000.0
        except Exception:
            continue
    return (len(items), round(total, 4))


def _is_3d(sk: Any) -> Optional[bool]:
    for name in ("Is3D", "GetSketchType"):
        try:
            v = getattr(sk, name)
            v = v() if callable(v) else v
            if name == "Is3D":
                return bool(v)
            # GetSketchType：0=2D，1=3D（部分版本）
            return bool(int(v) == 1)
        except Exception:
            continue
    return None


def start_3d_sketch(doc: Any) -> Dict[str, Any]:
    """开 3D 草图。判据：活动草图存在且 3D 标志为真。"""
    out = _result("sw_start_3d_sketch", "ISketchManager.Insert3DSketch")
    try:
        doc.SketchManager.Insert3DSketch(True)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    sk = doc.SketchManager.ActiveSketch
    flag = _is_3d(sk) if sk is not None else None
    out["detail"].update({"sketch_active": sk is not None, "is_3d": flag})
    out["checks"] = {"sketch_active": sk is not None}
    if flag is not None:
        out["checks"]["is_3d"] = bool(flag)
    out["ok"] = all(out["checks"].values()) if sk is not None else False
    return out


def trim(doc: Any, x_mm: float = 60.0, y_mm: float = 12.5,
         op: int = 0, sel_end: int = 0) -> Dict[str, Any]:
    """裁剪（在给定点处）。判据：线段数或总长变化。"""
    out = _result("sw_sketch_trim", "ISketchManager.SketchTrim(4 参)")
    before = seg_stats(doc)
    out["detail"].update({"point_mm": [x_mm, y_mm], "before": before})
    try:
        doc.SketchManager.SketchTrim(int(op), int(sel_end),
                                     float(x_mm) / 1000.0, float(y_mm) / 1000.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = seg_stats(doc)
    out["detail"]["after"] = after
    out["checks"] = {"geometry_changed": before != after}
    out["ok"] = out["checks"]["geometry_changed"]
    return out


def extend(doc: Any, x_mm: float = 0.0, y_mm: float = 60.0,
           z_mm: float = 0.0) -> Dict[str, Any]:
    """延伸（到给定点）。判据：线段总长增加。"""
    out = _result("sw_sketch_extend", "ISketchManager.SketchExtend(3 参)")
    before = seg_stats(doc)
    out["detail"].update({"point_mm": [x_mm, y_mm, z_mm], "before": before})
    try:
        # 实测：不选线段直接调无效（长度 20→20）。必须先选中要延伸的那条。
        _select_first_two_segments(doc) if False else None
        sk = doc.SketchManager.ActiveSketch
        segs = list(val(sk, "GetSketchSegments") or [])
        doc.ClearSelection2(True)
        if segs:
            segs[0].Select2(False, 0)
        doc.SketchManager.SketchExtend(float(x_mm) / 1000.0,
                                       float(y_mm) / 1000.0,
                                       float(z_mm) / 1000.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = seg_stats(doc)
    out["detail"]["after"] = after
    out["checks"] = {"length_increased": after[1] > before[1] + 1e-6}
    out["ok"] = out["checks"]["length_increased"]
    return out


def _select_first_two_segments(doc: Any) -> int:
    """选中活动草图的前两条线段（圆角/倒角前置）。"""
    try:
        sk = doc.SketchManager.ActiveSketch
        segs = list(val(sk, "GetSketchSegments") or [])
    except Exception:
        return 0
    doc.ClearSelection2(True)
    n = 0
    for seg in segs:
        try:
            seg.Select2(n > 0, 0)
            n += 1
        except Exception:
            continue
        if n >= 2:
            break
    return n


def fillet(doc: Any, radius_mm: float = 5.0) -> Dict[str, Any]:
    """草图圆角（需两条线段）。判据：线段数 +1。"""
    out = _result("sw_sketch_fillet", "ISketchManager.SketchFillet(1 参)")
    before = seg_stats(doc)
    picked = _select_first_two_segments(doc)
    out["detail"].update({"radius_mm": radius_mm, "selected": picked,
                          "before": before})
    if picked < 2:
        out["detail"]["error"] = "需要选中两条线段"
        return out
    try:
        # 真名是 **CreateFillet(Radius, ConstrainedCorners)**（2 参），不是 SketchFillet；
        # 且必须 comtypes 强类型（pywin32 报 <unknown>.SketchFillet）。
        from ._common import com_doc
        _sw, md = com_doc()
        md.SketchManager.CreateFillet(float(radius_mm) / 1000.0, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = seg_stats(doc)
    out["detail"]["after"] = after
    out["checks"] = {"segment_added": after[0] > before[0]}
    out["ok"] = out["checks"]["segment_added"]
    return out


def chamfer(doc: Any, distance_mm: float = 5.0, angle_deg: float = 45.0,
            option: int = 0) -> Dict[str, Any]:
    """草图倒角（需两条线段）。判据：线段数 +1。"""
    out = _result("sw_sketch_chamfer", "ISketchManager.SketchChamfer(3 参)")
    before = seg_stats(doc)
    picked = _select_first_two_segments(doc)
    out["detail"].update({"distance_mm": distance_mm, "selected": picked,
                          "before": before})
    if picked < 2:
        out["detail"]["error"] = "需要选中两条线段"
        return out
    try:
        # 真名是 **CreateChamfer(ChamferType:int, Dist1, Angle)**；第一参必须是 int
        from ._common import com_doc
        _sw, md = com_doc()
        md.SketchManager.CreateChamfer(int(option), float(distance_mm) / 1000.0,
                                       float(angle_deg) * 3.141592653589793 / 180.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = seg_stats(doc)
    out["detail"]["after"] = after
    out["checks"] = {"segment_added": after[0] > before[0]}
    out["ok"] = out["checks"]["segment_added"]
    return out


def convert_entities(doc: Any) -> Dict[str, Any]:
    """转换实体引用（需先选模型边）。判据：线段数 +1。"""
    out = _result("sw_sketch_convert_entities", "ISketchManager.SketchUseEdge()")
    before = seg_stats(doc)
    out["detail"]["before"] = before
    try:
        # pywin32 下 0 参调用报 DISP_E_PARAMNOTOPTIONAL → comtypes 强类型再试
        from ._common import com_doc
        _sw, md = com_doc()
        sm = md.SketchManager
        try:
            sm.SketchUseEdge()
        except TypeError:
            sm.SketchUseEdge2(False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = seg_stats(doc)
    out["detail"]["after"] = after
    out["checks"] = {"segment_added": after[0] > before[0]}
    out["ok"] = out["checks"]["segment_added"]
    return out
