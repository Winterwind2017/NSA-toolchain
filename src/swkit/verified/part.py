"""swkit.verified.part —— 零件/特征侧"实测通过"的实现（带自证）

每条都对应一次真实实测（`docs/RECIPES.md`），返回值统一是证据字典：

    {"ok": bool, "tool": str, "api": str, "detail": {...}, "checks": {...}}

覆盖：

| 工具 | 真实 API | 判据 |
|---|---|---|
| `bounding_box` | `IBody2.GetBodyBox`（0 参，6 个 double） | 尺寸 mm 与已知件一致 |
| `screenshot` | `IModelDoc2.SaveBMP(path, w, h)`（3 参） | 文件 > 0 字节 |
| `shell` | `IModelDoc2.InsertFeatureShell(thickness, byref ok)` | 特征数 +1（面 7→14） |
| `split_line` | `InsertSplitLineSil()` / `InsertSplitLineProject(True, False)` | 特征数 +1 |
| `thicken_surface` | `IModelDoc2.FeatureBossThicken(thk, dir, 0)` | 出现 `Thicken` 特征 |
| `offset_surface` | `IModelDoc2.InsertOffsetSurface(dist, flip)` | 曲面实体 +1 |
| `pattern_feature` | `FeatureLinearPattern3` / `FeatureCircularPattern3` | 特征数 +1 |

注意：`pattern_feature` 是**特征**阵列，标记与组件阵列**相反**——
特征 mark=4、方向 mark=1（见 `core/marks.py`）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from ..core.com import none_dispatch, val
from ..core.marks import FEATURE_DIR1, FEATURE_TO_PATTERN, NULL_DIMENSION_NAME
from ._common import (
    body_box, bodies, com_doc, count_features, exit_sketch, faces_of,
    iter_features, pick_face, shape_counts, wrap,
)

__all__ = ["bounding_box", "screenshot", "shell", "split_line", "thicken_surface",
           "offset_surface", "pattern_feature"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def bounding_box(doc_w: Any) -> Dict[str, Any]:
    """每个实体的包围盒（米 → 输出 mm）。"""
    out = _result("sw_get_bounding_box", "IBody2.GetBodyBox")
    bodies_ = bodies(doc_w, 0)
    out["detail"]["bodies"] = len(bodies_)
    rows = []
    for i, b in enumerate(bodies_):
        box = body_box(b)
        if box is None:
            continue
        rows.append({
            "body": i,
            "size_mm": [round((box[3] - box[0]) * 1000.0, 3),
                        round((box[4] - box[1]) * 1000.0, 3),
                        round((box[5] - box[2]) * 1000.0, 3)],
            "min_mm": [round(v * 1000.0, 3) for v in box[:3]],
            "max_mm": [round(v * 1000.0, 3) for v in box[3:]],
        })
    out["detail"]["boxes"] = rows
    out["checks"] = {"has_bodies": len(bodies_) > 0, "boxes_measured": len(rows) > 0}
    out["ok"] = all(out["checks"].values())
    return out


def screenshot(doc_w: Any, out_path: str, width: int = 1200,
               height: int = 800) -> Dict[str, Any]:
    """存 BMP 位图（PhotoView 的 COM 等价物；`SaveImage` 在本机不可用）。"""
    out = _result("sw_take_photoview_screenshot", "IModelDoc2.SaveBMP")
    path = os.path.abspath(out_path)
    out["detail"].update({"path": path, "width": int(width), "height": int(height)})
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    ok, res = _try([lambda: doc_w.SaveBMP(path, int(width), int(height)),
                    lambda: _com_save_bmp(path, int(width), int(height))])
    size = os.path.getsize(path) if os.path.exists(path) else 0
    out["detail"].update({"returned": str(res), "bytes": size})
    out["checks"] = {"file_written": size > 0}
    out["ok"] = all(out["checks"].values())
    return out


def _com_save_bmp(path: str, width: int, height: int):
    _sw, md = com_doc()
    return md.SaveBMP(path, width, height)


def shell(doc_w: Any, thickness: float, face_index: int = -1) -> Dict[str, Any]:
    """抽壳。`face_index=-1` 时自动选面积最大的面。"""
    out = _result("sw_shell", "IModelDoc2.InsertFeatureShell")
    exit_sketch(doc_w)
    before = shape_counts(doc_w)
    out["detail"]["before"] = before
    if face_index < 0:
        best, best_area = 0, -1.0
        for i, fc in enumerate(faces_of(bodies(doc_w, 0)[0]) if bodies(doc_w, 0) else []):
            try:
                box = list(val(wrap(fc), "GetBox"))
                dx, dy, dz = abs(box[3] - box[0]), abs(box[4] - box[1]), abs(box[5] - box[2])
                area = max(dx * dy, dx * dz, dy * dz)
                if area > best_area:
                    best, best_area = i, area
            except Exception:
                continue
        face_index = best
        out["detail"]["auto_face_area_mm2"] = round(best_area * 1e6, 2)
    selected, total = pick_face(doc_w, face_index)
    out["detail"].update({"face_index": face_index, "faces_total": total,
                          "selected": selected})
    if selected == 0:
        out["detail"]["error"] = "选面失败"
        return out

    def _pyw_shell():
        return doc_w.InsertFeatureShell(float(thickness))

    def _ct_shell():
        import ctypes
        _sw, md = com_doc()
        flag = ctypes.c_short(0)
        return md.InsertFeatureShell(float(thickness), ctypes.byref(flag))

    ok, res = _try([_pyw_shell, _ct_shell])
    after = shape_counts(doc_w)
    out["detail"].update({"after": after, "returned": str(res)})
    out["checks"] = {
        "feature_added": after["features"] > before["features"],
        "faces_increased": after["faces"] > before["faces"],
    }
    # 抽壳的可靠判据是"面数翻倍"（实测 7→14）；特征数在某些文档里读不到
    out["ok"] = out["checks"]["faces_increased"] or out["checks"]["feature_added"]
    return out


def split_line(doc_w: Any) -> Dict[str, Any]:
    """分割线：先试零参 `InsertSplitLineSil()`，再试 `InsertSplitLineProject(True, False)`。"""
    out = _result("sw_split_line", "InsertSplitLineSil / InsertSplitLineProject")
    exit_sketch(doc_w)
    faces = faces_of(bodies(doc_w, 0)[0]) if bodies(doc_w, 0) else []
    if not faces:
        out["detail"]["error"] = "没有可用面"
        return out
    before = count_features(doc_w)
    out["detail"].update({"faces": len(faces), "features_before": before})

    def _sil(idx: int, mark: int):
        doc_w.ClearSelection2(True)
        wrap(faces[idx]).Select2(False, mark)
        _sw, md = com_doc()
        return md.InsertSplitLineSil()

    for idx in range(min(3, len(faces))):
        for mark in (1, 0):
            ok, res = _try([lambda i=idx, m=mark: _sil(i, m)])
            if not ok:
                continue
            after = count_features(doc_w)
            if after > before:
                out["detail"].update({"path": "sil", "face": idx, "mark": mark,
                                      "features_after": after, "returned": str(res)})
                out["checks"] = {"feature_added": True}
                out["ok"] = True
                return out

    # 路径 B：草图 + 面
    try:
        doc_w.ClearSelection2(True)
        wrap(faces[0]).Select2(False, 0)
        skm = doc_w.SketchManager
        skm.InsertSketch(True)
        skm.CreateLine(-0.02, 0.0, 0.0, 0.02, 0.0, 0.0)
        skm.InsertSketch(True)
    except Exception as exc:                       # noqa: BLE001
        out["detail"]["sketch_error"] = str(exc)[:120]
    for toward in (False, True):
        def _proj(t=toward):
            doc_w.ClearSelection2(True)
            wrap(faces[0]).Select2(False, 1)
            _sw, md = com_doc()
            return md.InsertSplitLineProject(True, t)
        ok, res = _try([_proj])
        after = count_features(doc_w)
        if ok and after > before:
            out["detail"].update({"path": "project", "toward": toward,
                                  "features_after": after, "returned": str(res)})
            out["checks"] = {"feature_added": True}
            out["ok"] = True
            return out
    out["detail"]["features_after"] = count_features(doc_w)
    out["checks"] = {"feature_added": False}
    return out


def thicken_surface(doc_w: Any, thickness: float) -> Dict[str, Any]:
    """把曲面加厚成实体。前提：文档里有曲面实体。"""
    out = _result("sw_thicken_surface", "IModelDoc2.FeatureBossThicken")
    exit_sketch(doc_w)
    before = shape_counts(doc_w)
    out["detail"]["before"] = before
    surfs = bodies(doc_w, 1)
    if not surfs:
        out["detail"]["error"] = "没有曲面实体（先造一个曲面件）"
        return out
    faces = faces_of(surfs[0])
    if not faces:
        out["detail"]["error"] = "曲面没有面"
        return out

    def _thicken(mark: int, tdir: int):
        doc_w.ClearSelection2(True)
        wrap(faces[0]).Select2(False, mark)
        _sw, md = com_doc()
        return md.FeatureBossThicken(float(thickness), tdir, 0)

    made, attempts = False, []
    for mark in (1, 0):
        for tdir in (0, 1):
            ok, res = _try([lambda m=mark, t=tdir: _thicken(m, t)])
            nthk = sum(1 for f in iter_features(doc_w)
                       if val(f, "GetTypeName2") == "Thicken")
            after = shape_counts(doc_w)
            attempts.append({"mark": mark, "dir": tdir, "returned": str(res),
                             "thicken_features": nthk, "surfaces_after": after["surfaces"]})
            if nthk > 0 or after["surfaces"] < before["surfaces"]:
                made = True
                out["detail"]["after"] = after
                out["detail"]["thicken_features"] = nthk
                break
        if made:
            break
    out["detail"]["attempts"] = attempts
    out["checks"] = {"thicken_feature_present": made}
    out["ok"] = made
    return out


def offset_surface(doc_w: Any, distance: float) -> Dict[str, Any]:
    """偏移曲面。前提：有曲面实体；判据是曲面实体数 +1（返回值不可信）。"""
    out = _result("sw_offset_surface", "IModelDoc2.InsertOffsetSurface")
    exit_sketch(doc_w)
    surfs = bodies(doc_w, 1)
    out["detail"]["surfaces_before"] = len(surfs)
    if not surfs:
        out["detail"]["error"] = "没有曲面实体"
        return out
    faces = faces_of(surfs[0])
    if not faces:
        out["detail"]["error"] = "曲面没有面"
        return out

    def _offset(mark: int, flip: bool):
        doc_w.ClearSelection2(True)
        wrap(faces[0]).Select2(False, mark)
        _sw, md = com_doc()
        return md.InsertOffsetSurface(float(distance), flip)

    attempts = []
    for mark in (1, 0):
        for flip in (False, True):
            ok, res = _try([lambda m=mark, f=flip: _offset(m, f)])
            n1 = len(bodies(doc_w, 1))
            attempts.append({"mark": mark, "flip": flip, "returned": str(res),
                             "surfaces_after": n1})
            if n1 > len(surfs):
                out["detail"]["surfaces_after"] = n1
                out["detail"]["attempts"] = attempts
                out["checks"] = {"surface_added": True}
                out["ok"] = True
                return out
    out["detail"]["attempts"] = attempts
    out["checks"] = {"surface_added": False}
    return out


def _find_target_feature(doc_w: Any) -> Optional[Any]:
    """找最后一个切除类特征（ICE/Cut/CutFeature）——阵列的对象。"""
    target = None
    for fw in iter_features(doc_w):
        if val(fw, "GetTypeName2") in ("ICE", "Cut", "CutFeature"):
            target = fw
    return target


def _longest_line_edge(doc_w: Any) -> Tuple[Optional[Any], Optional[Any], float]:
    """返回 `(最长直边, 任一闭合边, 最长边长)`——方向参考候选。

    注意：`IEdge.GetCurve` 在本机不可用，改用 `GetCurveParams2`（前 6 个数是起止点）。
    """
    line_edge, circ_edge, best_len = None, None, -1.0
    for body in bodies(doc_w, 0):
        for face in faces_of(body):
            edges = val(wrap(face), "GetEdges") or []
            try:
                edges = list(edges)
            except TypeError:
                continue
            for edge in edges:
                p = val(wrap(edge), "GetCurveParams2")
                try:
                    p = list(p)
                except TypeError:
                    continue
                if len(p) < 6:
                    continue
                dx, dy, dz = p[3] - p[0], p[4] - p[1], p[5] - p[2]
                length = (dx * dx + dy * dy + dz * dz) ** 0.5
                if length > best_len:
                    best_len, line_edge = length, wrap(edge)
                if length < 1e-9 and circ_edge is None:
                    circ_edge = wrap(edge)
    return line_edge, circ_edge, best_len


def pattern_feature(doc_w: Any, kind: str = "linear", count: int = 3,
                    spacing: float = 0.02, angle_deg: float = 120.0) -> Dict[str, Any]:
    """**特征**阵列（不是组件阵列）。特征 mark=4、方向 mark=1。"""
    import math
    kind = (kind or "linear").lower()
    api = ("IFeatureManager.FeatureCircularPattern3" if kind == "circular"
           else "IFeatureManager.FeatureLinearPattern3")
    out = _result("sw_circular_pattern" if kind == "circular" else "sw_linear_pattern", api)
    exit_sketch(doc_w)
    target = _find_target_feature(doc_w)
    if target is None:
        out["detail"]["error"] = "找不到切除类特征（ICE/Cut）"
        return out
    line_edge, circ_edge, best_len = _longest_line_edge(doc_w)
    before = shape_counts(doc_w)
    out["detail"].update({
        "target": val(target, "Name"),
        "longest_edge_mm": round(best_len * 1000, 3) if best_len > 0 else None,
        "features_before": before["features"],
        "feature_mark": FEATURE_TO_PATTERN,
    })
    order = ([circ_edge, line_edge] if kind == "circular" else [line_edge, circ_edge])
    attempts = []
    for ent in order:
        for dmark in (FEATURE_DIR1, FEATURE_TO_PATTERN, 2):
            doc_w.ClearSelection2(True)
            try:
                target.Select2(False, FEATURE_TO_PATTERN)
                if ent is not None:
                    ent.Select2(True, dmark)
            except Exception as exc:               # noqa: BLE001
                attempts.append({"dmark": dmark, "error": str(exc)[:80]})
                continue
            selected = -1
            try:
                selected = int(doc_w.SelectionManager.GetSelectedObjectCount2(-1) or 0)
            except Exception:
                pass
            fm = doc_w.FeatureManager
            if kind == "circular":
                ok, res = _try([lambda: fm.FeatureCircularPattern3(
                    int(count), math.radians(float(angle_deg)), False,
                    NULL_DIMENSION_NAME, False, False)])
            else:
                ok, res = _try([lambda: fm.FeatureLinearPattern3(
                    int(count), float(spacing), 1, 0.0, False, False,
                    NULL_DIMENSION_NAME, NULL_DIMENSION_NAME, False, False)])
            after = shape_counts(doc_w)
            attempts.append({"dmark": dmark, "selected": selected,
                             "returned": str(res), "features_after": after["features"]})
            if after["features"] > before["features"]:
                out["detail"].update({"dmark": dmark, "selected": selected,
                                      "features_after": after["features"],
                                      "faces_after": after["faces"]})
                out["detail"]["attempts"] = attempts
                out["checks"] = {"feature_added": True}
                out["ok"] = True
                return out
    out["detail"]["attempts"] = attempts
    out["checks"] = {"feature_added": False}
    return out


def _try(thunks) -> Tuple[bool, Any]:
    """按顺序试多个调用，返回第一个不抛异常的结果。"""
    last: Any = None
    for fn in thunks:
        try:
            return True, fn()
        except Exception as exc:                  # noqa: BLE001
            last = "%s: %s" % (type(exc).__name__, exc)
    return False, last
