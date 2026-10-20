"""swkit.verified.sketch —— 草图侧实测通过的实现

| 工具 | 真实 API | 判据 |
|---|---|---|
| `construction` | `ISketchSegment.ConstructionGeometry`（属性） | True→False 往返成功 |
| `sketch_text` | `IModelDoc2.InsertSketchText(x,y,z,text,5 参)` | 草图线段数增加，或能读回文字 |
| `sketch_constraint` | `IModelDoc2.SketchAddConstraints("sgHORIZONTAL")` | 约束数 +1 **或**端点被真正拉平 |

为什么草图文字原来被判成"假成功"：审计去数**草图点/线**，而文字生成的是
`ISketch.GetSketchSegments` 里的**字形轮廓线段**——判据选错了。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.com import none_dispatch, val
from ._common import com_doc, exit_sketch, wrap

__all__ = ["construction", "sketch_text", "sketch_constraint"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _select_plane(doc_w: Any, plane: str) -> bool:
    try:
        doc_w.ClearSelection2(True)
        return bool(doc_w.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, False, 0,
                                                none_dispatch(), 0))
    except Exception:
        return False


def construction(doc_w: Any, plane: str = "前视基准面", length: float = 0.02,
                 leave_line: bool = False) -> Dict[str, Any]:
    """画一条线并把它切成构造线（并把开关来回切一次作为判据）。"""
    out = _result("sw_sketch_construction", "ISketchSegment.ConstructionGeometry")
    exit_sketch(doc_w)
    if not _select_plane(doc_w, plane):
        out["detail"]["error"] = "选不中基准面：%s" % plane
        return out
    skm = doc_w.SketchManager
    skm.InsertSketch(True)
    seg = skm.CreateLine(0.0, 0.0, 0.0, float(length), 0.0, 0.0)
    if seg is None:
        out["detail"]["error"] = "CreateLine 失败"
        return out
    s = wrap(seg)
    out["detail"]["before"] = bool(val(s, "ConstructionGeometry", False))
    try:
        s.ConstructionGeometry = True
        as_construction = bool(val(s, "ConstructionGeometry", False))
        s.ConstructionGeometry = False
        restored = bool(val(s, "ConstructionGeometry", True))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        skm.InsertSketch(True)
        return out
    if leave_line:
        try:
            s.ConstructionGeometry = True
        except Exception:
            pass
    skm.InsertSketch(True)
    out["detail"]["as_construction"] = as_construction
    out["detail"]["restored"] = restored
    out["checks"] = {"toggle_on": as_construction, "toggle_off": not restored}
    out["ok"] = all(out["checks"].values())
    return out


def sketch_text(doc_w: Any, text: str = "swkit", x: float = 0.0, y: float = 0.0,
                plane: str = "前视基准面") -> Dict[str, Any]:
    """在草图里写文字。判据：字形轮廓线段增加，或能读回文字。"""
    out = _result("sw_sketch_text", "IModelDoc2.InsertSketchText")
    exit_sketch(doc_w)
    if not _select_plane(doc_w, plane):
        out["detail"]["error"] = "选不中基准面：%s" % plane
        return out
    skm = doc_w.SketchManager
    skm.InsertSketch(True)

    def n_segments() -> int:
        try:
            sk = doc_w.SketchManager.ActiveSketch
            segs = val(sk, "GetSketchSegments") or []
            return len(list(segs))
        except Exception:
            return -1

    before = n_segments()
    _sw, md = com_doc()
    txt, used_shape = None, None
    for shape in ((0, 0, 0, 0, 0), (1, 1, 0, 0, 0), (0, 0, 24, 0, 0)):
        try:
            txt = md.InsertSketchText(float(x), float(y), 0.0, text,
                                      shape[0], shape[1], shape[2], shape[3], shape[4])
        except Exception as exc:                    # noqa: BLE001
            out["detail"].setdefault("attempts", []).append(
                {"shape": shape, "error": str(exc)[:80]})
            continue
        if txt is not None:
            used_shape = shape
            break
    after = n_segments()
    back = val(txt, "GetText") if txt is not None else None
    skm.InsertSketch(True)
    out["detail"].update({"segments_before": before, "segments_after": after,
                          "shape": used_shape, "text_readback": back})
    out["checks"] = {
        "object_created": txt is not None,
        "segments_increased": (after > before) if (before >= 0 and after >= 0) else False,
        "text_matches": bool(back and str(text) in str(back)),
    }
    out["ok"] = out["checks"]["object_created"] and (
        out["checks"]["segments_increased"] or out["checks"]["text_matches"])
    return out


def sketch_constraint(doc_w: Any, constraint: str = "sgHORIZONTAL",
                      plane: str = "前视基准面") -> Dict[str, Any]:
    """加草图约束。判据：约束数 +1，**或**端点真被拉平（几何证据）。"""
    out = _result("sw_add_sketch_constraint", "IModelDoc2.SketchAddConstraints")
    exit_sketch(doc_w)
    if not _select_plane(doc_w, plane):
        out["detail"]["error"] = "选不中基准面：%s" % plane
        return out
    skm = doc_w.SketchManager
    skm.InsertSketch(True)
    # 故意画一条略斜的线：水平约束若真生效，端点 Y 会被拉平成 0
    seg = skm.CreateLine(0.0, 0.0, 0.0, 0.03, 0.002, 0.0)
    if seg is None:
        out["detail"]["error"] = "CreateLine 失败"
        return out

    def n_constraints() -> int:
        try:
            cons = val(seg, "GetConstraints")
            return len(list(cons)) if cons else 0
        except Exception:
            return -1

    def end_point() -> Optional[tuple]:
        for name in ("GetEndPoint2", "GetEndPoint"):
            p = val(seg, name)
            if p is not None:
                try:
                    return (p.X, p.Y, p.Z)
                except Exception:
                    continue
        return None

    before_c, before_p = n_constraints(), end_point()
    try:
        seg.Select2(False, 0)
        _sw, md = com_doc()
        md.SketchAddConstraints(constraint)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        skm.InsertSketch(True)
        return out
    after_c, after_p = n_constraints(), end_point()
    skm.InsertSketch(True)
    flattened = bool(after_p and abs(after_p[1]) < 1e-9)
    out["detail"].update({
        "constraint": constraint,
        "constraints_before": before_c, "constraints_after": after_c,
        "end_y_before": round(before_p[1], 6) if before_p else None,
        "end_y_after": round(after_p[1], 6) if after_p else None,
        "flattened": flattened,
    })
    out["checks"] = {
        "constraint_count_increased": after_c > before_c,
        "geometry_flattened": flattened,
    }
    out["ok"] = (out["checks"]["constraint_count_increased"]
                 or out["checks"]["geometry_flattened"])
    return out
