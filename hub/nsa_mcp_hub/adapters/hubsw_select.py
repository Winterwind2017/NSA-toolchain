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


_ONFACE_SCHEMA = {
    "type": "object",
    "properties": {
        "face_index": {"type": "integer", "description": "面序号（从 0 开始）"},
        "body_index": {"type": "integer", "description": "实体序号，默认 0"},
    },
    "required": ["face_index"],
    "additionalProperties": False,
}


_BODIES_SCHEMA = {
    "type": "object",
    "properties": {
        "indices": {"type": "array", "items": {"type": "integer"},
                    "description": "实体序号列表（从 0 开始）"},
        "mark": {"type": "integer", "description": "选择标记，默认 0"},
        "append": {"type": "boolean", "description": "是否追加，默认 False"},
    },
    "required": ["indices"],
    "additionalProperties": False,
}


def _null_callout() -> Any:
    """`SelectByID2` 的 Callout 参数要 **VT_DISPATCH 的 NULL**，传 None 会「类型不匹配」。"""
    import pythoncom
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_DISPATCH, None)


_VIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string",
                 "description": "视图名（不给就选第一个子视图，即模型视图）"},
    },
    "additionalProperties": False,
}


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
        """按名字选中特征（支持中文特征名，如「凸台-拉伸1」）。

        踩过的坑：① `SelectByID2(name, "BODYFEATURE")` 对中文特征名恒 False；
        ② pywin32 的 `doc.FirstFeature()` 在本机报「找不到成员」；
        ③ comtypes 里 `FirstFeature`/`GetNextFeature` 返回的是 **dynamic
        _Dispatch**，且可能被包成 callable —— 必须 `value() if callable(value)
        else value` 解引用，否则 `GetNextFeature()` 抛 TypeError。
        走得通的路：comtypes QI 到 IModelDoc2 → 遍历整棵特征树 → `IFeature::Select2`。
        """
        append = bool(args.get("append"))
        names = [str(n) for n in (args.get("names") or []) if str(n).strip()]
        if not names:
            return normalize(KIT, "select_features", ok=False,
                             errors=["names 不能为空"])
        try:
            import comtypes
            import comtypes.client as cc
            import comtypes.gen.SldWorks as swmod
        except Exception as exc:            # noqa: BLE001
            return normalize(KIT, "select_features", ok=False,
                             errors=["comtypes 不可用：%s" % exc])
        comtypes.CoInitialize()
        try:
            cc.GetModule(r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")
        except Exception:                   # noqa: BLE001
            pass
        try:
            app = cc.GetActiveObject("SldWorks.Application")
            md = app.ActiveDoc.QueryInterface(swmod.IModelDoc2)
            if not append:
                md.ClearSelection2(True)

            def deref(value):
                return value() if callable(value) else value

            wanted = set(names)
            hits = []
            feat = deref(md.FirstFeature)
            guard = 0
            while feat is not None and guard < 500:
                guard += 1
                label = str(getattr(feat, "Name", "") or "")
                if label in wanted:
                    try:
                        if bool(feat.Select2(True, 0)):
                            hits.append(label)
                    except Exception:       # noqa: BLE001
                        pass
                try:
                    feat = deref(getattr(feat, "GetNextFeature"))
                except Exception:           # noqa: BLE001
                    break
            count = int(md.SelectionManager.GetSelectedObjectCount2(-1))
            checks = [{"check": "selected", "got": count, "want": len(names),
                       "ok": count == len(names)}]
            return normalize(KIT, "select_features", ok=count == len(names),
                             reads={"requested": names, "hits": hits,
                                    "features_scanned": guard,
                                    "selected_count": count},
                             checks=checks,
                             errors=[] if count == len(names)
                             else ["选中 %d 个（期望 %d）；hits=%s"
                                   % (count, len(names), hits)])
        except Exception as exc:            # noqa: BLE001
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

    def _sketch_on_face(args: Dict[str, Any]) -> Dict[str, Any]:
        """在实体面上开草图。

        swkit 的 `sw_create_sketch` 只接受**基准面名**，所以
        `sketch_text` / `convert_entities` / `circular_pattern` / `chamfer`
        这批"要在面上画"的工具一直用不了。这里补一层：选面 → InsertSketch(True)。
        """
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "create_sketch_on_face", ok=False,
                                 errors=["没有打开的文档"])
            body_index = int(args.get("body_index") or 0)
            bodies = doc.GetBodies2(0, True) or []
            if body_index >= len(bodies):
                return normalize(KIT, "create_sketch_on_face", ok=False,
                                 errors=["实体序号越界（共 %d 个）" % len(bodies)])
            faces = _seq(bodies[body_index], "GetFaces")
            index = int(args.get("face_index", 0))
            if not (0 <= index < len(faces)):
                return normalize(KIT, "create_sketch_on_face", ok=False,
                                 errors=["面序号越界（共 %d 个）" % len(faces)])
            doc.ClearSelection2(True)
            picked = bool(faces[index].Select2(True, 0))
            opened = bool(doc.SketchManager.InsertSketch(True))
            sketch = doc.SketchManager.ActiveSketch
            name = None
            try:
                name = getattr(sketch, "Name", None) if sketch is not None else None
            except Exception:            # noqa: BLE001
                name = None
            checks = [
                {"check": "face_selected", "got": picked, "want": True, "ok": picked},
                {"check": "sketch_open", "got": sketch is not None, "want": True,
                 "ok": sketch is not None},
            ]
            ok = all(c["ok"] for c in checks)
            return normalize(KIT, "create_sketch_on_face", ok=ok,
                             reads={"faces": len(faces), "face_index": index,
                                    "insert_returned": opened, "sketch": name},
                             checks=checks,
                             errors=[] if ok else ["选面=%s 开草图=%s"
                                                   % (picked, sketch is not None)])
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, "create_sketch_on_face", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    def _bodies(args: Dict[str, Any]) -> Dict[str, Any]:
        """按序号选实体。

        踩过三条路：
        * pywin32 `IBody2.Select2` → "instance can not be converted to a COM object"
        * comtypes `IPartDoc.GetBodies2` + `body.Select2` → `KeyError: 9`（生成的
          comtypes 模块解析不了该 dispid）
        * `SelectByID2("", "SOLIDBODY", 包围盒中心)` → 多实体时中心可能落在另一个
          实体里，导致两个序号选到同一个（实测 2 个实体只选中 1 个）

        最终方案：还是走 pywin32 的 `SelectByID2(SOLIDBODY)`，但取点改成
        **包围盒长边 5% 的内缩点**，躲开两个实体的重叠区。
        """
        indices = [int(i) for i in (args.get("indices") or [])]
        if not indices:
            return normalize(KIT, "select_bodies", ok=False, errors=["indices 不能为空"])
        append = bool(args.get("append"))
        mark = int(args.get("mark") or 0)
        try:
            app = _attach()
            doc = app.ActiveDoc
            if doc is None:
                return normalize(KIT, "select_bodies", ok=False, errors=["没有打开的文档"])
            bodies = doc.GetBodies2(0, True) or []
            if not append:
                doc.ClearSelection2(True)
            picked = []
            for index in indices:
                if not (0 <= index < len(bodies)):
                    continue
                box = bodies[index].GetBodyBox
                box = list(box() if callable(box) else (box or []))
                if len(box) < 6:
                    continue
                # 内缩 5%（各轴），避开多实体的重叠区
                def inset(lo: float, hi: float) -> float:
                    span = hi - lo
                    return lo + (span * 0.05 if span > 0 else 0.0)
                point = (inset(box[0], box[3]), inset(box[1], box[4]),
                         inset(box[2], box[5]))
                if bool(doc.Extension.SelectByID2("", "SOLIDBODY", point[0], point[1],
                                                  point[2], True, mark,
                                                  _null_callout(), 0)):
                    picked.append(index)
            count = _selected_count(doc)
            checks = [{"check": "bodies_selected", "got": len(picked),
                       "want": len(indices), "ok": len(picked) == len(indices)},
                      {"check": "selection_count", "got": count, "want": len(indices),
                       "ok": count == len(indices)}]
            ok = all(c["ok"] for c in checks)
            return normalize(KIT, "select_bodies", ok=ok,
                             reads={"bodies": len(bodies), "requested": indices,
                                    "picked": picked, "selected_count": count},
                             checks=checks,
                             errors=[] if ok else ["选中 %d/%d 个实体"
                                                   % (len(picked), len(indices))])
        except Exception as exc:             # noqa: BLE001
            return normalize(KIT, "select_bodies", ok=False,
                             errors=["%s: %s" % (type(exc).__name__, str(exc)[:200])])

    def _view(args: Dict[str, Any]) -> Dict[str, Any]:
        """选中图纸视图（孔表/剖视图/断裂视图的前置）。

        pywin32 的 `doc.GetFirstView()` 在本机报「找不到成员」，所以走 comtypes
        QI 到 `IDrawingDoc` 再枚举；`view.Name` 可能是属性也可能是方法，统一
        `value() if callable(value) else value`。Callout 必须是 None（comtypes 下
        传 win32com 的 VARIANT 会让第 8 个参数报 "VARIANT object has no
        attribute QueryInterface"）。
        """
        try:
            import comtypes
            import comtypes.client as cc
            import comtypes.gen.SldWorks as swmod
        except Exception as exc:             # noqa: BLE001
            return normalize(KIT, "select_view", ok=False,
                             errors=["comtypes 不可用：%s" % exc])
        comtypes.CoInitialize()
        try:
            cc.GetModule(r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")
        except Exception:                    # noqa: BLE001
            pass

        def deref(value: Any) -> Any:
            return value() if callable(value) else value

        try:
            app = cc.GetActiveObject("SldWorks.Application")
            raw = app.ActiveDoc
            doc = raw.QueryInterface(swmod.IDrawingDoc)
            md = raw.QueryInterface(swmod.IModelDoc2)
            views = []
            view = deref(doc.GetFirstView)
            guard = 0
            while view is not None and guard < 30:
                guard += 1
                views.append(view)
                view = deref(getattr(view, "GetNextView"))
            if not views:
                return normalize(KIT, "select_view", ok=False, errors=["图纸里没有视图"])
            wanted = str(args.get("name") or "").strip()

            def label_of(item: Any) -> Optional[str]:
                try:
                    return str(deref(getattr(item, "Name")) or "")
                except Exception:            # noqa: BLE001
                    return None

            target = None
            if wanted:
                for candidate in views:
                    if label_of(candidate) == wanted:
                        target = candidate
                        break
            if target is None:
                target = views[1] if len(views) > 1 else views[0]
            label = label_of(target) or ""
            md.ClearSelection2(True)
            ok = bool(md.Extension.SelectByID2(label, "DRAWINGVIEW", 0, 0, 0,
                                               False, 0, None, 0))
            count = int(md.SelectionManager.GetSelectedObjectCount2(-1))
            checks = [{"check": "view_selected", "got": ok, "want": True, "ok": ok},
                      {"check": "selection_count", "got": count, "want": 1,
                       "ok": count == 1}]
            good = all(c["ok"] for c in checks)
            return normalize(KIT, "select_view", ok=good,
                             reads={"views": len(views), "view": label,
                                    "selected_count": count},
                             checks=checks,
                             errors=[] if good else ["选不中视图 %r" % (label,)])
        except Exception as exc:             # noqa: BLE001
            return normalize(KIT, "select_view", ok=False,
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
        ToolSpec("sw_create_sketch_on_face",
                 "在实体面上开草图（swkit 的 create_sketch 只认基准面名，"
                 "面草图四件套靠它）。判据 = 选中面 + ActiveSketch 非空。",
                 _ONFACE_SCHEMA, _sketch_on_face, timeout_s=180),
        ToolSpec("sw_select_bodies",
                 "按序号选实体（combine/shell/scale 的前置选择）。"
                 "判据 = 每个序号都选中 + SelectionManager 计数一致。",
                 _BODIES_SCHEMA, _bodies, timeout_s=180),
        ToolSpec("sw_select_view",
                 "选中图纸视图（孔表/剖视图/断裂视图的前置）。判据 = SelectByID2 成功且计数=1。",
                 _VIEW_SCHEMA, _view, timeout_s=180),
    ]
