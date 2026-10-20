"""swkit.verified.drawing —— 出图侧实测通过的实现

**图纸夹具**（其余出图工具都依赖它）：

    d = new_drawing(part_path, template=A3, view="front")
    view = first_model_view(doc)      # 图纸里 Type != 1 的那个视图

出图类 API 的通用套路：**先在视图里选中实体（辅助实体 mark=1），再调零参/少参插入**，
判据一律用"符号计数"或"读回文本"——返回值不可信。

| 工具 | 真实 API | 判据 |
|---|---|---|
| `new_drawing` | `NewDocument(drwdot)` + `CreateDrawViewFromModelView3` | 视图数 ≥ 2 |
| `center_mark` | `IDrawingDoc.AddCenterMark(x, False)` | `IView.GetCenterMarks` 计数 +1 |
| `centerline` | `IDrawingDoc.InsertCenterLine()` | `IView.GetCenterLines` 计数 +1 |
| `symbol(kind)` | `InsertDatumTag2()` / `InsertGtol()` / `InsertWeldSymbol3()` | 返回对象非空且能读回文本 |
| `surface_finish` | `InsertSurfaceFinishSymbol2(15 参)` | 符号计数 +1 或对象非空 |
| `note` | `IModelDoc2.InsertNote(text)` + `GetAnnotation.SetPosition2` | 文本读回 + 位置读回 |

注意（实测）：中文版 `CreateDrawViewFromModelView3` **只认本地化视图名**（`*前视`），
传 `*Front` 返回 None；`IModelDocExtension` 不能直接 QI，要从 `md.Extension` 取。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, val
from ._common import com_app, com_doc, wrap

__all__ = ["new_drawing", "first_model_view", "center_mark", "centerline", "symbol",
           "surface_finish", "note", "VIEW_MAP", "DEFAULT_TEMPLATE"]

DEFAULT_TEMPLATE = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
                    r"\gb_a3.drwdot")

VIEW_MAP = {
    "front": "*前视", "back": "*后视", "left": "*左视", "right": "*右视",
    "top": "*上视", "bottom": "*下视", "isometric": "*等轴测",
    "trimetric": "*三轴测", "current": "*当前",
}


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def new_drawing(part_path: str, template: str = "", view: str = "front",
                x: float = 0.15, y: float = 0.15) -> Dict[str, Any]:
    """从零件新建 A3 图纸并插入一个模型视图。返回证据字典（`detail["title"]` 供后续用）。"""
    out = _result("sw_new_drawing", "IModelDocExtension.CreateDrawViewFromModelView3")
    tpl = template or DEFAULT_TEMPLATE
    if not os.path.isfile(tpl):
        out["detail"]["error"] = "图纸模板不存在：%s" % tpl
        return out
    if not os.path.isfile(part_path):
        out["detail"]["error"] = "模型不存在：%s" % part_path
        return out
    _sw, app_ct = com_app()
    doc = app_ct.NewDocument(tpl, 0, 0.0, 0.0)
    if isinstance(doc, tuple):
        doc = doc[-1]
    if doc is None:
        out["detail"]["error"] = "NewDocument 失败"
        return out
    doc_w = wrap(app_ct.ActiveDoc)
    name = view if str(view).startswith("*") else VIEW_MAP.get(str(view).lower(), view)
    view_obj = doc_w.CreateDrawViewFromModelView3(os.path.abspath(part_path),
                                                  name, float(x), float(y), 0.0)
    count = val(doc_w, "GetViewCount", 0)
    out["detail"].update({"title": val(doc_w, "GetTitle"),
                          "view_name_arg": name,
                          "views": count,
                          "view_created": view_obj is not None})
    out["checks"] = {"view_created": view_obj is not None, "views_at_least_two": (count or 0) >= 2}
    out["ok"] = all(out["checks"].values())
    return out


def first_model_view(doc_w: Any) -> Optional[Any]:
    """返回图纸里第一个模型视图（`Type != 1`；Type==1 是图纸本身）。"""
    v = val(doc_w, "GetFirstView")
    guard = 0
    while v is not None and guard < 30:
        guard += 1
        vw = wrap(v)
        if val(vw, "Type", 1) != 1:
            return vw
        v = val(vw, "GetNextView")
    return None


def _view_entities(view: Any, limit: int = 12) -> List[Any]:
    try:
        ents = view.GetVisibleEntities2(none_dispatch(), 1)
        return [wrap(e) for e in (ents or [])][:limit]
    except Exception:
        return []


def center_mark(doc_w: Any, x: float = 0.05) -> Dict[str, Any]:
    """在圆边上加中心标记。判据：`GetCenterMarks` 计数增加。"""
    out = _result("sw_add_center_mark", "IDrawingDoc.AddCenterMark")
    out["detail"]["doc_type"] = val(doc_w, "GetType", 0)
    view = first_model_view(doc_w)
    if view is None:
        out["detail"]["error"] = "图纸里没有模型视图"
        return out

    def n_marks() -> int:
        try:
            marks = val(view, "GetCenterMarks") or []
            return len(list(marks))
        except Exception:
            return -1

    before = n_marks()
    ents = _view_entities(view)
    circles = []
    for ee in ents:
        try:
            p = list(val(ee, "GetCurveParams2") or [])
            if len(p) >= 6:
                span = sum((p[3 + i] - p[i]) ** 2 for i in range(3)) ** 0.5
                if span < 1e-9:
                    circles.append(ee)
        except Exception:
            continue
    attempts = []
    called_ok = False
    for ee in (circles or ents):
        for mark in (1, 0, 2):
            try:
                doc_w.ClearSelection2(True)
                ee.Select2(False, mark)
            except Exception:
                continue
            for name in ("AddCenterMark", "InsertCenterMark"):
                try:
                    if name == "AddCenterMark":
                        res = doc_w.AddCenterMark(float(x), False)
                    else:
                        res = doc_w.InsertCenterMark(True, float(x), False, 0.0)
                    called_ok = True
                except Exception as exc:            # noqa: BLE001
                    attempts.append({"api": name, "mark": mark, "error": str(exc)[:60]})
                    continue
                attempts.append({"api": name, "mark": mark, "returned": str(res)})
        if n_marks() > before:
            break
    after = n_marks()
    out["detail"].update({"view": val(view, "Name"), "entities": len(ents),
                          "circles": len(circles), "marks_before": before,
                          "marks_after": after, "attempts": attempts[-6:]})
    out["checks"] = {"marks_increased": after > before}
    out["ok"] = out["checks"]["marks_increased"]
    return out


def centerline(doc_w: Any) -> Dict[str, Any]:
    """在两实体间加中心线。判据：`GetCenterLines` 计数增加。"""
    out = _result("sw_add_centerline", "IDrawingDoc.InsertCenterLine")
    view = first_model_view(doc_w)
    if view is None:
        out["detail"]["error"] = "图纸里没有模型视图"
        return out

    def n_lines() -> int:
        try:
            lines = val(view, "GetCenterLines") or []
            return len(list(lines))
        except Exception:
            return -1

    before = n_lines()
    pool = _view_entities(view, limit=8)
    out["detail"].update({"view": val(view, "Name"), "entities": len(pool),
                          "lines_before": before})
    if len(pool) < 2:
        out["detail"]["error"] = "可用实体不足两条"
        return out
    hit = None
    tried = 0
    for m1, m2 in ((1, 1), (1, 2), (4, 4), (2, 2), (0, 0)):
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                tried += 1
                try:
                    doc_w.ClearSelection2(True)
                    pool[i].Select2(False, m1)
                    pool[j].Select2(True, m2)
                    doc_w.InsertCenterLine()
                except Exception:
                    continue
                if n_lines() > before:
                    hit = {"marks": (m1, m2), "pair": (i, j)}
                    break
            if hit:
                break
        if hit:
            break
    after = n_lines()
    out["detail"].update({"tried": tried, "hit": hit, "lines_after": after})
    out["checks"] = {"lines_increased": after > before}
    out["ok"] = out["checks"]["lines_increased"]
    return out


def symbol(doc_w: Any, kind: str = "datum") -> Dict[str, Any]:
    """基准标记 / 形位公差 / 焊接符号（零参插入，先选实体）。"""
    api_map = {"datum": "InsertDatumTag2", "gtol": "InsertGtol",
               "weld": "InsertWeldSymbol3"}
    tool_map = {"datum": "sw_add_datum_feature", "gtol": "sw_add_gtol",
                "weld": "sw_add_weld_symbol"}
    kind = (kind or "datum").lower()
    if kind not in api_map:
        out = _result("sw_add_%s" % kind, "?")
        out["detail"]["error"] = "kind 只能是 datum / gtol / weld"
        return out
    out = _result(tool_map[kind], api_map[kind])
    view = first_model_view(doc_w)
    ents = _view_entities(view) if view is not None else []
    # IView 有专属计数器（TLB 实测）：datum→GetDatumTagCount / gtol→GetGTolCount /
    # weld→GetWeldSymbolCount。这才是"真的插进去了"的判据。
    counter = {"datum": "GetDatumTagCount", "gtol": "GetGTolCount",
               "weld": "GetWeldSymbolCount"}[kind]
    before = val(view, counter, None) if view is not None else None
    out["detail"].update({"kind": kind, "entities": len(ents),
                          "counter": counter, "count_before": before})
    if not ents:
        out["detail"]["error"] = "需要视图实体才能插入符号"
        return out
    _sw, md = com_doc()
    attempts = []
    for ent in ents[:3]:
        for mark in (1, 0):
            try:
                doc_w.ClearSelection2(True)
                ent.Select2(False, mark)
            except Exception:
                continue
            try:
                obj = getattr(md, api_map[kind])()
            except Exception as exc:                # noqa: BLE001
                attempts.append({"mark": mark, "error": str(exc)[:70]})
                continue
            text = _as_text(val(obj, "GetText") or val(obj, "Text"))
            count_after = val(view, counter, None)
            attempts.append({"mark": mark,
                             "object": type(obj).__name__ if obj is not None else None,
                             "text": text, "count_after": count_after})
            if obj is not None:
                out["detail"]["attempts"] = attempts
                out["detail"].update({"text": text, "count_after": count_after})
                out["checks"] = {
                    "object_created": _is_com(obj),
                    "count_increased": (count_after is not None
                                        and before is not None
                                        and count_after > before),
                    "text_readable": isinstance(text, str) and bool(text),
                }
                # 判据：对象是真 COM 对象，或计数确实 +1
                out["ok"] = (out["checks"]["object_created"]
                             or out["checks"]["count_increased"])
                return out
    out["detail"]["attempts"] = attempts
    out["checks"] = {"object_created": False, "count_increased": False}
    return out


def _is_com(obj: Any) -> bool:
    """是不是真的 COM 对象（插入类 API 有时只返回 True，那不算证据）。"""
    return obj is not None and not isinstance(obj, (bool, int, str, bytes))


def _as_text(v: Any) -> Optional[str]:
    """只在确实是字符串时才当文本；MethodCaller 之类一律返回 None。"""
    if isinstance(v, str):
        return v
    if v is None:
        return None
    try:
        if callable(v):
            r = v()
            return r if isinstance(r, str) else None
    except Exception:
        return None
    return None


def surface_finish(doc_w: Any, x: float = 0.05, y: float = 0.05) -> Dict[str, Any]:
    """表面粗糙度符号。判据：符号计数 +1 或返回对象非空。"""
    out = _result("sw_add_surface_finish", "InsertSurfaceFinishSymbol2/3")
    view = first_model_view(doc_w)

    def n_symbols() -> int:
        """-1 = 本机拿不到计数（而不是 0 个）。"""
        if view is None:
            return -1
        for name in ("GetSurfaceFinishSymbols", "GetSFSymbols"):
            v = val(view, name)
            if v is None:
                continue
            try:
                return len(list(v))
            except TypeError:
                continue
        return -1

    before = n_symbols()
    _sw, md = com_doc()
    try:
        ext = md.Extension.QueryInterface(_sw.IModelDocExtension)
    except Exception:
        ext = md.Extension
    made, attempts = None, []
    shapes = [
        (1, 0, float(x), float(y), 0.0, 0, 0, "", "", "", "", "", "", ""),
        (0, 0, float(x), float(y), 0.0, 0, 0, "", "", "", "", "", "", ""),
    ]
    for shape in shapes:
        for api_name, obj in (("InsertSurfaceFinishSymbol2", md),
                              ("InsertSurfaceFinishSymbol3", ext)):
            try:
                res = getattr(obj, api_name)(*shape)
            except Exception as exc:                # noqa: BLE001
                attempts.append({"api": api_name, "error": str(exc)[:70]})
                continue
            attempts.append({"api": api_name, "returned": str(res)})
            if res is not None:
                made = res
                break
        if made is not None:
            break
    after = n_symbols()
    out["detail"].update({"view": val(view, "Name") if view is not None else None,
                          "symbols_before": before, "symbols_after": after,
                          "attempts": attempts,
                          "note": ("本机没有任何可读计数：IView 只有 "
                                   "GetFirstCenterMark/GetDatumTagCount 这类，"
                                   "**没有** GetSurfaceFinishSymbols；"
                                   "InsertSurfaceFinishSymbol2 只返回 True。"
                                   "因此无法证明符号真的生成 → 判为不可验证。")})
    out["checks"] = {
        "call_returned_true": any(a.get("returned") == "True" for a in attempts),
        "count_available": after >= 0,
        "symbols_increased": after > before,
    }
    # 只有拿到"计数确实 +1"才算验证通过；只返回 True 不算证据
    out["ok"] = out["checks"]["symbols_increased"]
    out["status"] = "unverified" if not out["ok"] else "verified"
    return out


def note(doc_w: Any, text: str = "swkit", x: float = 0.05, y: float = 0.05) -> Dict[str, Any]:
    """插入注释并设位置。判据：文本读回 + 位置读回。"""
    out = _result("sw_note", "IModelDoc2.InsertNote")
    _sw, md = com_doc()
    try:
        obj = md.InsertNote(text)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if obj is None:
        out["detail"]["error"] = "InsertNote 返回 None"
        return out
    read_text = val(obj, "GetText")
    pos = None
    try:
        ann = val(obj, "GetAnnotation")
        if ann is not None:
            ann.SetPosition2(float(x), float(y), 0.0)
            pos = list(val(ann, "GetPosition") or [])
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["position_error"] = str(exc)[:80]
    out["detail"].update({"text": read_text, "position": [round(v, 6) for v in pos] if pos else None})
    out["checks"] = {"text_read_back": bool(read_text),
                     "position_set": bool(pos) and abs(pos[0] - float(x)) < 1e-6}
    out["ok"] = all(out["checks"].values())
    return out
