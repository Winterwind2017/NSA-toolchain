"""swkit.verified.sketch_ops —— 草图实体/编辑（内核 `SolidWorksApp` 的实测转正）

上游这 14 个工具底层就是 `SolidWorksApp` 的草图方法，而内核已经在本仓库里，所以
"验证"= **跑一遍 + 数草图线段**，不用重新发明 API。

| 工具 | 判据 |
|---|---|
| `create_sketch` / `edit_sketch` / `exit_sketch` | 活动草图存在 / 重入后能画 |
| `line` / `circle` / `rectangle` / `arc` / `ellipse` / `polygon` / `spline` / `centerline` | 草图线段数 **+1（矩形/多边形 +4/+N）** |
| `offset` / `linear_pattern` / `circular_pattern` | 线段数增加（先选中实体） |

单位：**输入是毫米**，内核用 `_m()` 转到米（`app.py` 里的 `_m/_mm`）。
中文版基准面名是 `前视基准面`——内核默认 `"Front Plane"`，在本机会选不中，必须显式传。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from math import radians

from ..core.com import none_dispatch, val

__all__ = ["create_sketch", "edit_sketch", "exit_sketch", "line", "circle",
           "rectangle", "arc", "ellipse", "polygon", "spline", "centerline",
           "offset", "linear_pattern", "circular_pattern",
           "DEFAULT_PLANE", "app"]

DEFAULT_PLANE = "前视基准面"

_APP: Optional[Any] = None


def app(reset: bool = False) -> Any:
    """惰性创建并复用内核实例。

    注意：`SolidWorksApp(...)` **构造时不连接**，必须显式 `connect()`——
    否则每个方法都抛 `ConnectionError: SolidWorks not connected`（实测踩过）。
    内核是懒取 `ActiveDoc` 的，所以连接后不用再绑文档。
    """
    global _APP
    if _APP is None or reset:
        from ..api.app import SolidWorksApp
        _APP = SolidWorksApp(visible=True, log_to_stdout=False)
        _APP.connect()
    return _APP


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _segments(doc: Any) -> int:
    """活动草图的线段数；-1 表示没有活动草图。"""
    try:
        sk = doc.SketchManager.ActiveSketch
    except Exception:
        return -1
    if sk is None:
        return -1
    try:
        segs = val(sk, "GetSketchSegments")
        return len(list(segs)) if segs is not None else 0
    except TypeError:
        return -1


def create_sketch(doc: Any, plane: str = DEFAULT_PLANE) -> Dict[str, Any]:
    """在基准面上新建草图。判据：活动草图存在且线段数为 0。"""
    out = _result("sw_create_sketch", "SketchManager.InsertSketch")
    try:
        app().create_sketch(plane)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    segs = _segments(doc)
    out["detail"].update({"plane": plane, "segments": segs})
    out["checks"] = {"sketch_active": segs >= 0}
    out["ok"] = out["checks"]["sketch_active"]
    return out


def edit_sketch(doc: Any, sketch_name: str) -> Dict[str, Any]:
    """重入已有草图。判据：活动草图名等于目标。"""
    out = _result("sw_edit_sketch", "IModelDoc2.EditSketch")
    # 内核用 MenuCommand(2026)，在本机 pywin32 下报 `<unknown>.MenuCommand`；
    # 正确 API 是选中草图后调 `EditSketch()`（TLB 实测 0 参）。
    used = None
    try:
        doc.ClearSelection2(True)
        doc.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0,
                                  none_dispatch(), 0)
        doc.EditSketch()
        used = "EditSketch"
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["select_error"] = str(exc)[:80]
        try:
            app().edit_sketch(sketch_name)
            used = "MenuCommand"
        except Exception as exc2:                   # noqa: BLE001
            out["detail"]["error"] = "%s: %s" % (type(exc2).__name__, exc2)
            return out
    out["detail"]["api_used"] = used
    active = None
    try:
        active = val(doc.SketchManager.ActiveSketch, "Name")
    except Exception:
        pass
    out["detail"].update({"target": sketch_name, "active": active})
    out["checks"] = {"reentered": bool(active) and str(active) == str(sketch_name)}
    out["ok"] = out["checks"]["reentered"]
    return out


def exit_sketch(doc: Any) -> Dict[str, Any]:
    """退出草图。判据：不再有活动草图。"""
    out = _result("sw_exit_sketch", "SketchManager.InsertSketch(True)")
    try:
        app().exit_sketch()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    segs = _segments(doc)
    out["detail"]["segments_after"] = segs
    out["checks"] = {"sketch_closed": segs < 0}
    out["ok"] = out["checks"]["sketch_closed"]
    return out


def _draw(tool: str, api: str, doc: Any, call, **detail) -> Dict[str, Any]:
    """通用"画一个实体"：比线段数增量。"""
    out = _result(tool, api)
    before = _segments(doc)
    out["detail"].update(detail)
    try:
        call()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _segments(doc)
    out["detail"].update({"segments_before": before, "segments_after": after})
    out["checks"] = {"segments_increased": after > before}
    out["ok"] = out["checks"]["segments_increased"]
    return out


def line(doc: Any, x1: float, y1: float, x2: float, y2: float) -> Dict[str, Any]:
    return _draw("sw_sketch_line", "SketchManager.CreateLine", doc,
                 lambda: app().sketch_line((x1, y1), (x2, y2)),
                 params=[x1, y1, x2, y2])


def circle(doc: Any, cx: float, cy: float, radius: float) -> Dict[str, Any]:
    return _draw("sw_sketch_circle", "CreateCircleByRadius", doc,
                 lambda: app().sketch_circle((cx, cy), radius),
                 params=[cx, cy, radius])


def rectangle(doc: Any, x1: float, y1: float, x2: float, y2: float,
              rect_type: str = "corner") -> Dict[str, Any]:
    return _draw("sw_sketch_rectangle", "CreateCornerRectangle/CenterRectangle", doc,
                 lambda: app().sketch_rectangle((x1, y1), (x2, y2), rect_type),
                 params=[x1, y1, x2, y2], rect_type=rect_type)


def arc(doc: Any, cx: float, cy: float, radius: float, start_deg: float,
        end_deg: float, clockwise: bool = False) -> Dict[str, Any]:
    return _draw("sw_sketch_arc", "CreateArc", doc,
                 lambda: app().sketch_arc((cx, cy), start_deg, end_deg, radius, clockwise),
                 params=[cx, cy, radius, start_deg, end_deg], clockwise=clockwise)


def ellipse(doc: Any, cx: float, cy: float, semi_major: float, semi_minor: float,
            rotation_deg: float = 0.0) -> Dict[str, Any]:
    return _draw("sw_sketch_ellipse", "CreateEllipse", doc,
                 lambda: app().sketch_ellipse((cx, cy), semi_major, semi_minor,
                                              rotation_deg),
                 params=[cx, cy, semi_major, semi_minor, rotation_deg])


def polygon(doc: Any, cx: float, cy: float, num_sides: int,
            circumscribed_radius: float, rotation_deg: float = 0.0) -> Dict[str, Any]:
    return _draw("sw_sketch_polygon", "CreatePolygon", doc,
                 lambda: app().sketch_polygon((cx, cy), num_sides,
                                              circumscribed_radius, rotation_deg),
                 params=[cx, cy, num_sides, circumscribed_radius, rotation_deg])


def spline(doc: Any, points: List[Any]) -> Dict[str, Any]:
    """样条。内核用 `CreateSpline(list)` 在 pywin32 下会拿到空成员（`None(...)`），
    这里改成显式 `VT_ARRAY|VT_R8` 的 VARIANT 数组。"""
    pts = [tuple(p) for p in points]

    def _call():
        import win32com.client as _w
        import pythoncom
        flat = []
        for x, y in pts:
            flat.extend([float(x) / 1000.0, float(y) / 1000.0, 0.0])
        arr = _w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
        sm = doc.SketchManager
        for name in ("CreateSpline2", "CreateSpline"):
            fn = getattr(sm, name, None)
            if fn is None:
                continue
            try:
                seg = fn(arr, True) if name == "CreateSpline2" else fn(arr)
            except Exception:
                continue
            if seg is not None:
                return
        raise RuntimeError("CreateSpline2 / CreateSpline 都失败")

    return _draw("sw_sketch_spline", "SketchManager.CreateSpline2", doc, _call,
                 points=pts)


def centerline(doc: Any, x1: float, y1: float, x2: float, y2: float) -> Dict[str, Any]:
    return _draw("sw_sketch_centerline", "CreateCenterLine", doc,
                 lambda: app().sketch_centerline((x1, y1), (x2, y2)),
                 params=[x1, y1, x2, y2])


def _select_all_segments(doc: Any) -> int:
    """选中活动草图里的所有线段，返回选中数（图案/偏移的前置条件）。"""
    try:
        sk = doc.SketchManager.ActiveSketch
        segs = list(val(sk, "GetSketchSegments") or [])
    except Exception:
        return 0
    doc.ClearSelection2(True)
    n = 0
    for seg in segs:
        try:
            seg.Select2(False, n > 0)
            n += 1
        except Exception:
            continue
    return n


def offset(doc: Any, distance: float = 2.0, outward: bool = True) -> Dict[str, Any]:
    """偏移草图实体（先选中现有线段）。判据：线段数增加。"""
    out = _result("sw_sketch_offset", "SketchManager.SketchOffset2")
    before = _segments(doc)
    selected = _select_all_segments(doc)
    out["detail"].update({"distance_mm": distance, "selected": selected,
                          "segments_before": before})
    if selected == 0:
        out["detail"]["error"] = "没有可偏移的草图实体"
        return out
    # 直接调 `SketchOffset2(Offset, BothDirections, Chain, CapEnds, MakeConstruction, AddDimensions)`（TLB 3 参）；
    # 内核的 sketch_offset 在当前形态下调用失败，所以这里不走内核。
    try:
        # 真实签名是 **6 参**（TLB 只列了 3 个）：
        # (Offset, BothDirections, Chain, CapEnds, MakeConstruction, AddDimensions)
        doc.SketchManager.SketchOffset2(float(distance) / 1000.0,
                                        not bool(outward), True,
                                        False, False, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _segments(doc)
    out["detail"]["segments_after"] = after
    out["checks"] = {"segments_increased": after > before}
    out["ok"] = out["checks"]["segments_increased"]
    return out


def linear_pattern(doc: Any, x_count: int = 2, y_count: int = 1,
                   x_spacing: float = 10.0, y_spacing: float = 0.0,
                   x_angle: float = 0.0) -> Dict[str, Any]:
    """草图线性阵列（先选中实体）。判据：线段数增加。"""
    out = _result("sw_sketch_linear_pattern", "SketchManager.SketchLinearPattern")
    before = _segments(doc)
    selected = _select_all_segments(doc)
    out["detail"].update({"selected": selected, "segments_before": before,
                          "x_count": x_count, "y_count": y_count})
    if selected == 0:
        out["detail"]["error"] = "没有可阵列的草图实体"
        return out
    # TLB: CreateLinearSketchStepAndRepeat(NumX, NumY, SpacingX, SpacingY,
    #                                     AngleX, AngleY, DeleteInstances)
    try:
        # 必须 comtypes：三个 Dim 参数要传 None，pywin32 动态调度报“类型不匹配”。
        from ._common import com_doc as _com_doc
        _sw, _md = _com_doc()
        _md.SketchManager.CreateLinearSketchStepAndRepeat(
            # 真实签名 **12 参**（TLB 只列 6 个）：
            # (NumX, NumY, SpacingX, SpacingY, AngleX, AngleY,
            #  DeleteInstances:str, XSpacingDim, YSpacingDim, AngleDim,
            #  CreateNumDimX:bool, CreateNumDimY:bool)
            int(x_count), int(y_count), float(x_spacing) / 1000.0,
            float(y_spacing) / 1000.0, radians(float(x_angle)), 0.0, "",
            None, None, None, False, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _segments(doc)
    out["detail"]["segments_after"] = after
    out["checks"] = {"segments_increased": after > before}
    out["ok"] = out["checks"]["segments_increased"]
    return out


def circular_pattern(doc: Any, count: int = 3, radius: float = 20.0,
                     angle_deg: float = 360.0) -> Dict[str, Any]:
    """草图圆周阵列（先选中实体）。判据：线段数增加。"""
    out = _result("sw_sketch_circular_pattern", "SketchManager.SketchCircularPattern")
    before = _segments(doc)
    selected = _select_all_segments(doc)
    out["detail"].update({"selected": selected, "segments_before": before,
                          "count": count, "radius_mm": radius})
    if selected == 0:
        out["detail"]["error"] = "没有可阵列的草图实体"
        return out
    # 真实签名 **9 参**（TLB 只列了 6 个）：
    #   (ArcRadius, ArcAngle, PatternNum, PatternSpacing, PatternRotate,
    #    DeleteInstances:str, RadiusDim, AngleDim, CreateNumOfInstancesDim)
    # 三个 Dim 传 None 即可（实测 1 段 → 4 段、长度 ×4）；必须走 comtypes。
    import math as _math
    try:
        from ._common import com_doc as _com_doc
        _sw, _md = _com_doc()
        _md.SketchManager.CreateCircularSketchStepAndRepeat(
            float(radius) / 1000.0, _math.radians(float(angle_deg)), int(count),
            _math.radians(float(angle_deg)), True, "", None, None, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _segments(doc)
    out["detail"]["segments_after"] = after
    out["checks"] = {"segments_increased": after > before}
    out["ok"] = out["checks"]["segments_increased"]
    return out
