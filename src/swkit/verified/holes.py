"""swkit.verified.holes —— 螺纹孔（底孔 + 口部倒角 + 真实螺纹）

## 为什么要自己画，不用孔向导

`sldworks.tlb` 里 `IFeatureManager.HoleWizard5` 是**27 参**；旧 kernel 只传 14 个，
从第 3 个参数起整体错位（StandardIndex 落 0 = ANSI 英寸、SSize 位置被塞深度数值、
Diameter=0 = 用默认），于是永远得到「2 英寸 = Ø50.8」。把 27 参按 TLB 顺序改对、
孔类型常量也按 `swWzd*` 改对（`swWzdHole=2`）之后实测：6 组（standard 0/1/2 ×
size 空/M6）**全部返回 None、体积分毫未变** —— 孔向导在 COM 下连特征都不建
（Toolbox 是装了的，不是缺标准件库）。所以本机要交付螺纹孔，只能按
`docs/RECIPES.md` §3 的配方自己画。

## 配方（每一步都有几何判据，不靠返回值）

1. **底孔**：选面 → `InsertSketch(True)` → `CreateCircleByRadius(底孔半径)` →
   `InsertSketch(True)` 退出 → 选草图 → `FeatureCut4`（29 参，盲孔或贯穿）
2. **口部倒角**：在实体上找「半径≈底孔半径、圆心在孔口平面」的圆边 →
   `Select2(False, 1)` → `InsertFeatureChamfer(0, 1, 距, 45°, 0,0,0,0)`
3. **真实螺纹**：`CreateDefinition(87 = swFmSweepThread)` → `ThreadFeatureData` →
   `edge.Select2(False, 1)`（标记必须 = 1）→ 设 `Type="Metric Tap"` /
   `ThreadMethod=0` / `EndCondition=0` / `BlindDepth` / `Pitch` / `Size` /
   `PitchOverride=True` / `DiameterOverride=False` / `RightHanded=True` → `CreateFeature`
4. **降级**：真实螺纹失败时用 `InsertCosmeticThread3`（装饰螺纹），并如实标注
   `thread_kind="cosmetic"`，判据不把它当"真实螺纹"

## 判据（`delivery_gate_passed`）

* `has_tap_drill_cut`：实测圆柱直径 = 规格表底孔直径（±0.15 mm）
* `has_mouth_chamfer`：孔口出现锥面（`ISurface::IsCone`）
* `thread_kind`：`real`（ThreadFeatureData 建成）/ `cosmetic`（降级）/ `none`
* 三者都满足才算可交付；`ok` 就等于 `delivery_gate_passed`

## 实测踩到的三个坑（都已在代码里处理）

1. **`SelectByID2("", "FACE", 点)` 在原点/边上会失败**：块体的顶面中心正好是
   (0,0,0)，直接点选返回 False。所以 `_select_face_by_point` 带 4 组微偏移重试，
   还失败就 `_select_top_face` 兜底：挑「`IsPlane` 且法向 z>0.9」的最高面，
   用**面对象自己的 `Select2(False, 0)`** 选中（这条最稳）。
2. **`val()` 只接受 3 个参数**（obj, name, default）：早先写成
   `val(face, "Select2", False, 0)` 会 TypeError 被吞掉 → 面选不上。多参数方法要用
   `getattr(obj, "Select2")(False, 0)`。
3. **贯穿孔**：`FeatureCut4` 必须用 `swEndCondThroughAll=1` 且深度传 0（盲孔才是 0+深度）；
   而 `ThreadFeatureData` **没有"贯穿"枚举**（只有 Blind/Revolutions/UpToSelection），
   所以贯穿孔的螺纹按 `BlindDepth = 深度` 给。

单位：对外 **mm**，内部转米。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..core.com import none_dispatch, val
from ._common import bodies, com_doc, faces_of, shape_counts, wrap

__all__ = ["threaded_hole", "TAP_DRILL_MM", "TAP_PITCH_MM"]

# 规格表（与 docs/RECIPES.md §3 一致）：底孔直径 mm / 螺距 mm
TAP_DRILL_MM = {"M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0,
                "M8": 6.8, "M10": 8.5, "M12": 10.2}
TAP_PITCH_MM = {"M3": 0.5, "M4": 0.7, "M5": 0.8, "M6": 1.0,
                "M8": 1.25, "M10": 1.5, "M12": 1.75}
# 公称直径（螺纹大小径标注用）
NOMINAL_MM = {"M3": 3.0, "M4": 4.0, "M5": 5.0, "M6": 6.0,
              "M8": 8.0, "M10": 10.0, "M12": 12.0}

SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 1
SW_START_SKETCH = 0
SW_FM_SWEEP_THREAD = 87
SW_THREAD_METHOD_CUT = 0
SW_THREAD_END_BLIND = 0
SW_COSMETIC_STANDARD_ISO = 8
SW_COSMETIC_END_BLIND = 0
SW_COSMETIC_END_THROUGH = 2


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _size_key(size: str) -> str:
    key = str(size or "").strip().upper()
    for sep in ("X", "×", " "):
        if sep in key:
            key = key.split(sep)[0]
    return key


def _volume_mm3(doc: Any) -> Optional[float]:
    try:
        _sw, md = com_doc()
        mp = md.Extension.CreateMassProperty()
        volume = mp.Volume
        return float(volume) * 1e9 if volume is not None else None
    except Exception:                              # noqa: BLE001
        return None


def _cylinders_and_cones(doc_w: Any,
                         debug: Optional[List[str]] = None) -> Tuple[List[float], int]:
    """扫实体上的圆柱面/锥面：返回 (圆柱直径 mm 列表, 锥面个数)。"""
    diameters: List[float] = []
    cones = 0
    try:
        all_bodies = bodies(doc_w, 0)
    except Exception as exc:                       # noqa: BLE001
        if debug is not None:
            debug.append("bodies: %s: %s" % (type(exc).__name__, str(exc)[:80]))
        return diameters, cones
    if debug is not None:
        debug.append("bodies=%d" % len(all_bodies))
    for body in all_bodies:
        for face in faces_of(body):
            try:
                surf = val(wrap(face), "GetSurface")
            except Exception as exc:               # noqa: BLE001
                if debug is not None:
                    debug.append("GetSurface: %s: %s" % (type(exc).__name__, str(exc)[:70]))
                continue
            if surf is None:
                continue
            try:
                is_cyl = val(surf, "IsCylinder")
                if debug is not None:
                    debug.append("face: cylinder=%s type=%s"
                                 % (is_cyl, type(surf).__name__))
                if is_cyl:
                    params = list(val(surf, "CylinderParams") or [])
                    if len(params) >= 7:
                        diameters.append(round(float(params[6]) * 2000.0, 3))
                    elif debug is not None:
                        debug.append("CylinderParams 长度=%d" % len(params))
                    continue
            except Exception as exc:               # noqa: BLE001
                if debug is not None:
                    debug.append("IsCylinder: %s: %s" % (type(exc).__name__, str(exc)[:70]))
            try:
                if val(surf, "IsCone"):
                    cones += 1
            except Exception:                      # noqa: BLE001
                pass
    return sorted(diameters), cones


def _find_mouth_edge(doc_w: Any, radius_mm: float,
                     z_mm: Optional[float] = None,
                     tol_mm: float = 0.2,
                     debug: Optional[List[str]] = None) -> Optional[Any]:
    """找「半径≈底孔半径、圆心在孔口平面」的圆边（返回 comtypes 边对象）。"""
    best = None
    best_dz = None
    edge_total = 0
    circle_total = 0
    for body in bodies(doc_w, 0):
        for face in faces_of(body):
            try:
                edges = list(val(wrap(face), "GetEdges") or [])
            except Exception as exc:               # noqa: BLE001
                if debug is not None:
                    debug.append("GetEdges: %s: %s" % (type(exc).__name__, str(exc)[:60]))
                continue
            edge_total += len(edges)
            for edge in edges:
                try:
                    curve = val(edge, "GetCurve")
                    if curve is None or not val(curve, "IsCircle"):
                        continue
                    params = list(val(curve, "CircleParams") or [])
                except Exception as exc:           # noqa: BLE001
                    if debug is not None:
                        debug.append("edge: %s: %s" % (type(exc).__name__, str(exc)[:70]))
                    continue
                if len(params) < 7:
                    continue
                circle_total += 1
                radius = float(params[6]) * 1000.0
                if abs(radius - radius_mm) > tol_mm:
                    continue
                cz = float(params[2]) * 1000.0
                dz = abs(cz - z_mm) if z_mm is not None else 0.0
                if best is None or (best_dz is not None and dz < best_dz):
                    best, best_dz = edge, dz
    if debug is not None:
        debug.append("edges=%d circles=%d want_r=%.3f found=%s"
                     % (edge_total, circle_total, radius_mm, best is not None))
    return best


def _select_face_by_point(doc: Any, point_mm: Tuple[float, float, float]) -> bool:
    """按点选面；点正好落在原点/边上时 SelectByID2 会失败，所以带微偏移重试。"""
    x, y, z = [float(v) / 1000.0 for v in point_mm]
    offsets = [(0.0, 0.0, 0.0), (0.001, 0.001, 0.0), (-0.001, 0.001, 0.0),
               (0.001, -0.001, 0.0), (-0.001, -0.001, 0.0)]
    for dx, dy, dz in offsets:
        try:
            ok = doc.Extension.SelectByID2("", "FACE", x + dx, y + dy, z + dz,
                                           False, 0, None, 0)
            if ok:
                return True
        except Exception:                          # noqa: BLE001
            continue
    return False


def _select_top_face(doc: Any,
                     debug: Optional[List[str]] = None) -> Tuple[bool, Optional[float]]:
    """兜底：挑**法向朝 +Z 的平面**里最高的那张，用它自己的 GetBox 中心点选它。

    返回值 `(selected, z_mm)`；`z_mm` 是该面的高度，调用方可以据此判断孔口平面。
    """
    doc_w = doc
    best = None                                    # (z, point)
    try:
        all_bodies = bodies(doc_w, 0)
    except Exception as exc:                       # noqa: BLE001
        if debug is not None:
            debug.append("bodies: %s: %s" % (type(exc).__name__, str(exc)[:70]))
        return False, None
    face_index = 0
    for body in all_bodies:
        for face in faces_of(body):
            face_w = wrap(face)
            face_index += 1
            try:
                surf = val(face_w, "GetSurface")
                is_plane = bool(val(surf, "IsPlane")) if surf is not None else False
                normal = list(val(face_w, "Normal") or [])
                if surf is None or not is_plane:
                    continue
                if len(normal) < 3 or float(normal[2]) < 0.9:
                    continue
                box = list(val(face_w, "GetBox") or [])
                if len(box) < 6:
                    continue
                z_mid = (float(box[2]) + float(box[5])) / 2.0
                point = ((float(box[0]) + float(box[3])) / 2.0,
                         (float(box[1]) + float(box[4])) / 2.0,
                         float(box[5]))
                if best is None or z_mid > best[0]:
                    best = (z_mid, point, face_w)
            except Exception as exc:               # noqa: BLE001
                if debug is not None and len(debug) < 10:
                    debug.append("face: %s: %s" % (type(exc).__name__, str(exc)[:70]))
                continue
    if debug is not None:
        debug.append("best=%s" % (None if best is None else round(best[0] * 1000.0, 3)))
    if best is None:
        return False, None
    z_mid, point, face_w = best
    # 直接对该面对象 Select2：点选在原点/边上会失败，面对象选择最稳
    selected = False
    try:
        fn = getattr(face_w, "Select2")
        selected = bool(fn(False, 0))
    except Exception as exc:                       # noqa: BLE001
        if debug is not None:
            debug.append("Select2: %s: %s" % (type(exc).__name__, str(exc)[:70]))
        selected = False
    if not selected:
        selected = _select_face_by_point(doc, tuple(v * 1000.0 for v in point))
    if debug is not None:
        debug.append("selected=%s z=%.3f" % (selected, z_mid * 1000.0))
    return bool(selected), round(z_mid * 1000.0, 3)


def threaded_hole(doc: Any, size: str = "M6", depth_mm: float = 12.0,
                  through: bool = False,
                  hole_x_mm: float = 0.0, hole_y_mm: float = 0.0,
                  face_point_mm: Optional[Tuple[float, float, float]] = None,
                  mouth_chamfer_mm: float = 0.5,
                  with_thread: bool = True,
                  right_handed: bool = True) -> Dict[str, Any]:
    """螺纹孔：底孔 + 口部倒角 + 真实螺纹（失败降级装饰螺纹）。

    参数
    ----
    size : "M6"/"M12" 之类；底孔直径与螺距查 `TAP_DRILL_MM` / `TAP_PITCH_MM`
    depth_mm : 底孔深度（mm），`through=True` 时忽略
    through : 是否贯穿
    hole_x_mm / hole_y_mm : 孔心在**所选面草图坐标**里的位置（mm）
    face_point_mm : 给定则先按该点选面（否则用当前选择）
    mouth_chamfer_mm : 口部倒角距离（0 = 不做）
    with_thread : False 时只做底孔+倒角（用于对照实验）
    """
    out = _result("sw_threaded_hole",
                  "FeatureCut4 + InsertFeatureChamfer + ThreadFeatureData(87)")
    key = _size_key(size)
    tap_d = TAP_DRILL_MM.get(key)
    pitch = TAP_PITCH_MM.get(key, 1.0)
    nominal = NOMINAL_MM.get(key)
    out["detail"].update({
        "size": size, "size_key": key, "tap_drill_mm": tap_d,
        "pitch_mm": pitch, "nominal_mm": nominal,
        "depth_mm": depth_mm, "through": bool(through),
        "mouth_chamfer_mm": mouth_chamfer_mm, "with_thread": bool(with_thread),
    })
    if tap_d is None:
        out["detail"]["error"] = ("不支持的规格 %r：只支持 %s"
                                 % (size, "/".join(sorted(TAP_DRILL_MM))))
        return out

    before_vol = _volume_mm3(doc)
    before = shape_counts(doc)
    out["detail"]["volume_before_mm3"] = before_vol
    out["detail"]["features_before"] = before.get("features")

    # ── ① 选面 + 草图 + 圆 ───────────────────────────────────────
    face_selected = True
    face_source = "current_selection"
    if face_point_mm is not None:
        face_selected = _select_face_by_point(doc, face_point_mm)
        face_source = "point"
        if not face_selected:
            face_pick_debug: List[str] = []
            face_selected, top_z = _select_top_face(doc, debug=face_pick_debug)
            out["detail"]["face_pick_debug"] = face_pick_debug[:10]
            face_source = "auto_top_face(z=%s mm)" % top_z
            out["detail"]["face_auto_z_mm"] = top_z
    out["detail"]["face_source"] = face_source
    if not face_selected:
        out["detail"]["error"] = "选面失败：face_point_mm 处没有可用的面"
        return out
    sketch_open = False
    try:
        doc.SketchManager.InsertSketch(True)       # 在选中的面上开草图
        sketch_open = True
        segment = doc.SketchManager.CreateCircleByRadius(
            float(hole_x_mm) / 1000.0, float(hole_y_mm) / 1000.0, 0.0,
            (float(tap_d) / 2.0) / 1000.0)
        if segment is None:
            raise RuntimeError("CreateCircleByRadius 返回 None（草图没开？）")
        doc.SketchManager.InsertSketch(True)       # 退出草图
        sketch_open = False
    except Exception as exc:                       # noqa: BLE001
        out["detail"]["error"] = "草图阶段失败：%s: %s" % (type(exc).__name__, exc)
        if sketch_open:
            try:
                doc.SketchManager.InsertSketch(True)
            except Exception:                      # noqa: BLE001
                pass
        return out

    # 退出草图后新草图是选中的；FeatureCut4 用 AutoSelect 吃掉它
    # 贯穿必须用 swEndCondThroughAll=1 + 深度 0；盲孔用 0 + 真实深度
    end_type = SW_END_COND_THROUGH_ALL if through else SW_END_COND_BLIND
    depth_m = 0.0 if through else float(depth_mm) / 1000.0
    cut_args = [
        True, False, False,
        int(end_type),
        SW_END_COND_BLIND,
        depth_m, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        False,                                     # NormalCut
        True,                                      # UseFeatScope
        True,                                      # UseAutoSelect ← 必须 True
        False,
        True,
        True,
        SW_START_SKETCH,
        0.0, False, False,
    ]
    try:
        cut_feat = doc.FeatureManager.FeatureCut4(*cut_args)
    except Exception as exc:                       # noqa: BLE001
        out["detail"]["error"] = "FeatureCut4 失败：%s: %s" % (type(exc).__name__, exc)
        return out
    out["detail"]["cut_feature"] = val(cut_feat, "Name") if cut_feat is not None else None
    after_cut_vol = _volume_mm3(doc)
    out["detail"]["volume_after_cut_mm3"] = after_cut_vol

    # ── ② 口部倒角 ───────────────────────────────────────────────
    scan_debug: List[str] = []
    mouth_edge = _find_mouth_edge(doc, float(tap_d) / 2.0, debug=scan_debug)
    out["detail"]["mouth_edge_found"] = mouth_edge is not None
    if mouth_edge is not None and mouth_chamfer_mm > 0:
        try:
            mouth_edge.Select2(False, 1)
            chamfer = doc.FeatureManager.InsertFeatureChamfer(
                0, 1, float(mouth_chamfer_mm) / 1000.0,
                math.pi / 4.0, 0.0, 0.0, 0.0, 0.0)
            out["detail"]["chamfer_feature"] = (
                val(chamfer, "Name") if chamfer is not None else None)
        except Exception as exc:                   # noqa: BLE001
            out["detail"]["chamfer_error"] = "%s: %s" % (type(exc).__name__, exc)

    # ── ③ 真实螺纹（失败降级装饰螺纹）─────────────────────────────
    thread_kind = "none"
    if with_thread:
        edge_for_thread = _find_mouth_edge(doc, float(tap_d) / 2.0, debug=scan_debug)
        if edge_for_thread is None:
            out["detail"]["thread_error"] = "找不到孔口圆边"
        else:
            try:
                edge_for_thread.Select2(False, 1)  # 标记必须 = 1
                data = doc.FeatureManager.CreateDefinition(SW_FM_SWEEP_THREAD)
                data.Edge = edge_for_thread
                data.Type = "Metric Tap"
                data.ThreadMethod = SW_THREAD_METHOD_CUT
                data.EndCondition = SW_THREAD_END_BLIND
                data.BlindDepth = float(depth_mm) / 1000.0
                data.Pitch = float(pitch) / 1000.0
                data.Size = "%sx%s" % (key, pitch)
                data.PitchOverride = True
                data.DiameterOverride = False
                data.RightHanded = bool(right_handed)
                thread_feat = doc.FeatureManager.CreateFeature(data)
                if thread_feat is not None:
                    thread_kind = "real"
                    out["detail"]["thread_feature"] = val(thread_feat, "Name")
                else:
                    out["detail"]["thread_error"] = "CreateFeature 返回 None"
            except Exception as exc:               # noqa: BLE001
                out["detail"]["thread_error"] = "%s: %s" % (type(exc).__name__, exc)
        if thread_kind != "real" and nominal is not None:
            try:
                return_value = doc.FeatureManager.InsertCosmeticThread3(
                    SW_COSMETIC_STANDARD_ISO, "Tapped Hole", "%s" % key,
                    float(nominal) / 1000.0,
                    SW_COSMETIC_END_THROUGH if through else SW_COSMETIC_END_BLIND,
                    float(depth_m), "")
                if return_value:
                    thread_kind = "cosmetic"
            except Exception as exc:               # noqa: BLE001
                out["detail"]["cosmetic_error"] = "%s: %s" % (type(exc).__name__, exc)

    # ── ④ 量几何（判据只看几何）────────────────────────────────────
    after_vol = _volume_mm3(doc)
    after = shape_counts(doc)
    diameters, cones = _cylinders_and_cones(doc, debug=scan_debug)
    out["detail"]["scan_debug"] = scan_debug[:14]
    bore = min(diameters, key=lambda d: abs(d - float(tap_d))) if diameters else None
    tap_ok = (bore is not None and abs(bore - float(tap_d)) <= 0.15)
    chamfer_ok = cones > 0
    out["detail"].update({
        "volume_after_mm3": after_vol,
        "volume_delta_mm3": (round(after_vol - before_vol, 3)
                             if (before_vol is not None and after_vol is not None) else None),
        "features_after": after.get("features"),
        "faces_after": after.get("faces"),
        "cylinders_mm": diameters,
        "bore_diameter_mm": bore,
        "cone_faces": cones,
        "thread_kind": thread_kind,
    })
    out["checks"] = {
        "has_tap_drill_cut": bool(tap_ok),
        "has_mouth_chamfer": bool(chamfer_ok),
        "thread_present": thread_kind != "none",
        "real_thread": thread_kind == "real",
    }
    out["detail"]["delivery_gate_passed"] = bool(
        tap_ok and chamfer_ok and thread_kind != "none")
    out["ok"] = out["detail"]["delivery_gate_passed"]
    if not out["ok"]:
        out["detail"].setdefault(
            "error",
            "未达交付门槛：底孔=%s（期望 Ø%.2f）、倒角=%s、螺纹=%s"
            % (bore, float(tap_d), chamfer_ok, thread_kind))
    return out
