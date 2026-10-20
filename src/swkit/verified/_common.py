"""swkit.verified._common —— 零件侧共用的选择/计数/几何小工具

都是被 fixpack 反复验证过的写法，搬进来时只做了封装，没有改语义：

* `pick_face` 用 `IFace2.Select2`（**不依赖坐标命中**，这是本机最稳的选面方式）；
* 计数一律用 `FirstFeature` 遍历 + `GetBodies2`，因为返回值不可信；
* comtypes 只在"必须强类型"的调用上用（`InsertFeatureShell` / `FeatureBossThicken` /
  `InsertOffsetSurface` / `InsertSplitLineSil` / `SaveBMP`），其余走 pywin32。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..core.com import comtypes_bundle, none_dispatch, pyw, val

__all__ = ["wrap", "sw_module", "com_app", "com_doc", "count_features", "bodies", "faces_of", "pick_face",
           "exit_sketch", "body_box", "shape_counts"]

_CT_CACHE: Dict[str, Any] = {}


def wrap(obj: Any) -> Any:
    if obj is None:
        return None
    try:
        return pyw().Dispatch(obj)
    except Exception:
        return obj


def sw_module(tlb_path: Optional[str] = None) -> Any:
    """返回 comtypes 生成的 sldworks 模块（缓存的），用于 QI 到具体接口。"""
    key = tlb_path or "default"
    if key not in _CT_CACHE:
        _CT_CACHE[key] = comtypes_bundle(tlb_path)
    return _CT_CACHE[key][0]


def com_app(tlb_path: Optional[str] = None) -> Tuple[Any, Any]:
    """返回 `(sw_module, Application)`；comtypes 模块与 Application 只建一次。"""
    key = tlb_path or "default"
    if key not in _CT_CACHE:
        _CT_CACHE[key] = comtypes_bundle(tlb_path)
    return _CT_CACHE[key]


def com_doc(tlb_path: Optional[str] = None) -> Tuple[Any, Any]:
    """返回 `(sw_module, IModelDoc2)`。"""
    sw, app = com_app(tlb_path)
    md = app.ActiveDoc.QueryInterface(sw.IModelDoc2)
    return sw, md


def iter_features(doc_w: Any):
    """遍历特征树。`FirstFeature` / `GetNextFeature` 在 pywin32 下是**属性**，
    在 comtypes 下是**方法**——这里用 `val()` 统一，调用失败时它返回属性本身。"""
    feat = val(doc_w, "FirstFeature")
    guard = 0
    while feat is not None and guard < 2000:
        guard += 1
        fw = wrap(feat)
        yield fw
        nxt = val(fw, "GetNextFeature")
        if nxt is feat:            # 属性调用失败时 val 会原样返回，避免死循环
            break
        feat = nxt


def count_features(doc_w: Any) -> int:
    return sum(1 for _ in iter_features(doc_w))


def bodies(doc_w: Any, body_type: int = 0) -> List[Any]:
    """`body_type`: 0=实体，1=曲面。"""
    try:
        return list(doc_w.GetBodies2(body_type, True) or [])
    except Exception:
        return []


def faces_of(body: Any) -> List[Any]:
    faces = val(wrap(body), "GetFaces") or []
    try:
        return list(faces)
    except TypeError:
        return []


def pick_face(doc_w: Any, index: int = 0, mark: int = 1) -> Tuple[int, int]:
    """按索引选面，返回 `(选中数, 面总数)`。"""
    faces = faces_of(bodies(doc_w, 0)[0]) if bodies(doc_w, 0) else []
    if not faces:
        return 0, 0
    if index < 0 or index >= len(faces):
        index = 0
    f = wrap(faces[index])
    try:
        doc_w.ClearSelection2(True)
    except Exception:
        pass
    for m in (mark, 0):
        try:
            f.Select2(False, m)
            n = int(doc_w.SelectionManager.GetSelectedObjectCount2(-1) or 0)
            if n > 0:
                return n, len(faces)
        except Exception:
            continue
    # 回退：按面中心坐标选
    try:
        box = list(f.GetBox)
        cx, cy, cz = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0,
                      (box[2] + box[5]) / 2.0)
        doc_w.Extension.SelectByID2("", "FACE", cx, cy, cz, False, mark,
                                    none_dispatch(), 0)
        n = int(doc_w.SelectionManager.GetSelectedObjectCount2(-1) or 0)
        return n, len(faces)
    except Exception:
        return 0, len(faces)


def exit_sketch(doc_w: Any) -> bool:
    """若草图为打开状态，先退出（否则后续选面/画线都会失败）。"""
    try:
        sk = doc_w.SketchManager.ActiveSketch
        if sk is not None:
            doc_w.SketchManager.InsertSketch(True)
            return True
    except Exception:
        pass
    return False


def body_box(body: Any) -> Optional[List[float]]:
    try:
        box = list(val(wrap(body), "GetBodyBox"))
        if len(box) == 6:
            return [float(v) for v in box]
    except Exception:
        pass
    return None


def shape_counts(doc_w: Any) -> Dict[str, int]:
    """`{features, solids, surfaces, faces}`——所有判据的基线。"""
    solid = bodies(doc_w, 0)
    surf = bodies(doc_w, 1)
    faces = 0
    for b in solid + surf:
        faces += len(faces_of(b))
    return {"features": count_features(doc_w), "solids": len(solid),
            "surfaces": len(surf), "faces": faces}
