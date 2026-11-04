"""SW 选择类 hub 工具：草图实体 / 特征的选择。

## 为什么需要

swkit 有一批工具**必须先选中对象**才生效（草图圆角/倒角/剪裁/转换实体/圆周阵列、
特征阵列/镜像）：它们内部不自己选，调用方又没有任何"按名字/序号选中"的工具，
于是这些工具在验收里永远是 `ok=false`（判据：数量没变化）。

实测（2026-11-04）：`ISketchSegment::Select2(False, 0)` 能选中草图线段，
`SelectionManager.GetSelectedObjectCount2(-1)` 读得到数量。

## 工具

* `sw_select_sketch_segments(indices=[0,1], append=False)` —— 在当前**编辑中的草图**里
  按序号选线段（不传 indices 就是全选）；
* `sw_select_features(names=["Sketch1"], append=False)` —— 按名字选特征/草图；
* `sw_select_faces(indices=[...], body_index=0, append=False)` —— 按序号选实体面
  （钣金 `insert_bends`、抽壳、拔模、转换实体都要它）；
* `sw_select_edges(indices=[...], append=False)` —— 按序号选边（倒角/圆角/转换实体）。

实测（2026-11-04）：`IFace2::Select2(True, 0)` 可用；`GetEdges` 是**属性**（tuple），
`GetFaces()` 是**方法**（要加括号）—— 这两个极易混。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..tools import ToolSpec, normalize

KIT = "sw"

_SEG_SCHEMA = {
    "type": "object",
    "properties": {
        "indices": {"type": "array", "items": {"type": "integer"},
                    "description": "要选中的草图线段序号（从 0 开始）；不传=全选"},
        "append": {"type": "boolean",
                   "description": "是否追加到已选集合（默认 False，先清空）"},
    },
    "additionalProperties": False,
}

_FEAT_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {"type": "array", "items": {"type": "string"},
                  "description": "特征/草图名字，如 Sketch1、凸台-拉伸1"},
        "append": {"type": "boolean",
                   "description": "是否追加到已选集合（默认 False，先清空）"},
    },
    "required": ["names"],
    "additionalProperties": False,
}


_FACE_SCHEMA = {
    "type": "object",
    "properties": {
        "indices": {"type": "array", "items": {"type": "integer"},
                    "description": "面序号（从 0 开始，按实体 GetFaces 顺序）"},
        "body_index": {"type": "integer", "description": "实体序号，默认 0"},
        "append": {"type": "boolean", "description": "是否追加（默认 False 先清空）"},
    },
    "required": ["indices"],
    "additionalProperties": False,
}

_EDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "indices": {"type": "array", "items": {"type": "integer"},
                    "description": "边序号（按该面 GetEdges 顺序，或整个实体的边）"},
        "face_index": {"type": "integer",
                       "description": "先按这个面序号取它的边（不传=用实体全部边）"},
        "body_index": {"type": "integer", "description": "实体序号，默认 0"},
        "append": {"type": "boolean", "description": "是否追加（默认 False 先清空）"},
    },
    "required": ["indices"],
    "additionalProperties": False,
}


def _seq(obj: Any, name: str) -> List[Any]:
    """取集合属性：本机 SolidWorks 有的集合是**方法**（GetFaces()）、有的是**属性**
    （GetEdges）—— 混着用，所以这里统一处理，别再踩 tuple not callable。"""
    try:
        attr = getattr(obj, name)
    except Exception:                    # noqa: BLE001
        return []
    try:
        value = attr() if callable(attr) else attr
    except Exception:                    # noqa: BLE001
        return []
    try:
        return list(value or [])
    except TypeError:
        return []


def _attach() -> Any:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("SldWorks.Application")


def _selected_count(doc: Any) -> int:
    try:
        return int(doc.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:                    # noqa: BLE001
        return -1


def select_tools() -> List[Any]:
    def _segments(args: Dict[str, Any]) -> Dict[str, Any]:
        append = bool(args.get("append"))
        indices = args.get("indices")
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "select_sketch_segments", ok=False,
                                 errors=["没有打开的文档"])
            sketch = doc.SketchManager.ActiveSketch
            if sketch is None:
                return normalize(KIT, "select_sketch_segments", ok=False,
                                 errors=["当前没有编辑中的草图（先 sw_create_sketch）"])
            segs = list(sketch.GetSketchSegments or [])
            if not append:
                doc.ClearSelection2(True)
            if indices:
                targets = [int(i) for i in indices]
            else:
                targets = list(range(len(segs)))
            picked = []
            for i in targets:
                if i < 0 or i >= len(segs):
                    continue
                try:
                    ok = bool(segs[i].Select2(True, 0))
                except Exception:        # noqa: BLE001
                    ok = False
                if ok:
                    picked.append(i)
            count = _selected_count(doc)
            checks = [
                {"check": "segments_found", "got": len(segs), "want": ">=1",
                 "ok": len(segs) >= 1},
                {"check": "selected", "got": count, "want": len(targets),
                 "ok": count == len(targets)},
            ]
            return normalize(KIT, "select_sketch_segments",
                             ok=count == len(targets),
                             reads={"segments": len(segs), "selected_count": count,
                                    "picked": picked},
                             checks=checks,
                             errors=[] if count == len(targets)
                             else ["选中数 %d ≠ 期望 %d" % (count, len(targets))])
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, "select_sketch_segments", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    def _features(args: Dict[str, Any]) -> Dict[str, Any]:
        append = bool(args.get("append"))
        names = [str(n) for n in (args.get("names") or []) if str(n).strip()]
        if not names:
            return normalize(KIT, "select_features", ok=False,
                             errors=["names 不能为空"])
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "select_features", ok=False,
                                 errors=["没有打开的文档"])
            if not append:
                doc.ClearSelection2(True)
            hits = []
            for name in names:
                for kind in ("BODYFEATURE", "SKETCH"):
                    try:
                        if doc.Extension.SelectByID2(name, kind, 0, 0, 0,
                                                     True, 0, None, 0):
                            hits.append(name)
                            break
                    except Exception:    # noqa: BLE001
                        continue
            count = _selected_count(doc)
            checks = [
                {"check": "selected", "got": count, "want": len(names),
                 "ok": count == len(names)},
            ]
            return normalize(KIT, "select_features", ok=count == len(names),
                             reads={"requested": names, "hits": hits,
                                    "selected_count": count},
                             checks=checks,
                             errors=[] if count == len(names)
                             else ["选中 %d 个（期望 %d）" % (count, len(names))])
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, "select_features", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    def _faces(args: Dict[str, Any]) -> Dict[str, Any]:
        indices = [int(i) for i in (args.get("indices") or [])]
        if not indices:
            return normalize(KIT, "select_faces", ok=False, errors=["indices 不能为空"])
        append = bool(args.get("append"))
        body_index = int(args.get("body_index") or 0)
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "select_faces", ok=False, errors=["没有打开的文档"])
            bodies = doc.GetBodies2(0, True) or []
            if body_index >= len(bodies):
                return normalize(KIT, "select_faces", ok=False,
                                 errors=["实体序号越界（共 %d 个）" % len(bodies)])
            faces = _seq(bodies[body_index], "GetFaces")
            if not append:
                doc.ClearSelection2(True)
            picked = []
            for i in indices:
                if 0 <= i < len(faces) and faces[i].Select2(True, 0):
                    picked.append(i)
            count = _selected_count(doc)
            checks = [
                {"check": "faces_found", "got": len(faces), "want": ">=1",
                 "ok": len(faces) >= 1},
                {"check": "selected", "got": count, "want": len(indices),
                 "ok": count == len(indices)},
            ]
            return normalize(KIT, "select_faces", ok=count == len(indices),
                             reads={"faces": len(faces), "selected_count": count,
                                    "picked": picked},
                             checks=checks,
                             errors=[] if count == len(indices)
                             else ["选中 %d 个（期望 %d）" % (count, len(indices))])
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, "select_faces", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    def _edges(args: Dict[str, Any]) -> Dict[str, Any]:
        indices = [int(i) for i in (args.get("indices") or [])]
        if not indices:
            return normalize(KIT, "select_edges", ok=False, errors=["indices 不能为空"])
        append = bool(args.get("append"))
        body_index = int(args.get("body_index") or 0)
        face_index = args.get("face_index")
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "select_edges", ok=False, errors=["没有打开的文档"])
            bodies = doc.GetBodies2(0, True) or []
            if body_index >= len(bodies):
                return normalize(KIT, "select_edges", ok=False,
                                 errors=["实体序号越界（共 %d 个）" % len(bodies)])
            body = bodies[body_index]
            if face_index is None:
                edges = _seq(body, "GetEdges")
            else:
                faces = _seq(body, "GetFaces")
                if int(face_index) >= len(faces):
                    return normalize(KIT, "select_edges", ok=False,
                                     errors=["面序号越界（共 %d 个）" % len(faces)])
                edges = _seq(faces[int(face_index)], "GetEdges")
            if not append:
                doc.ClearSelection2(True)
            picked = []
            for i in indices:
                if 0 <= i < len(edges) and edges[i].Select2(True, 0):
                    picked.append(i)
            count = _selected_count(doc)
            checks = [
                {"check": "edges_found", "got": len(edges), "want": ">=1",
                 "ok": len(edges) >= 1},
                {"check": "selected", "got": count, "want": len(indices),
                 "ok": count == len(indices)},
            ]
            return normalize(KIT, "select_edges", ok=count == len(indices),
                             reads={"edges": len(edges), "selected_count": count,
                                    "picked": picked},
                             checks=checks,
                             errors=[] if count == len(indices)
                             else ["选中 %d 个（期望 %d）" % (count, len(indices))])
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, "select_edges", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    return [
        ToolSpec("sw_select_sketch_segments",
                 "在当前编辑中的草图里按序号选线段（草图圆角/倒角/剪裁/转换实体/"
                 "圆周阵列的前置选择）。判据 = SelectionManager 选中数。",
                 _SEG_SCHEMA, _segments, timeout_s=180),
        ToolSpec("sw_select_features",
                 "按名字选特征或草图（特征阵列/镜像的前置选择）。判据 = 选中数。",
                 _FEAT_SCHEMA, _features, timeout_s=180),
        ToolSpec("sw_select_faces",
                 "按序号选实体面（钣金 insert_bends / 抽壳 / 拔模 / 转换实体的前置选择）。"
                 "判据 = SelectionManager 选中数。",
                 _FACE_SCHEMA, _faces, timeout_s=180),
        ToolSpec("sw_select_edges",
                 "按序号选边（可先指定 face_index 取该面的边；倒角/圆角/转换实体用）。"
                 "判据 = 选中数。",
                 _EDGE_SCHEMA, _edges, timeout_s=180),
    ]
