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
           "surface_finish", "note", "aux_view", "section_view", "broken_view",
           "drawing_dimension", "hole_table", "VIEW_MAP", "DEFAULT_TEMPLATE"]

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
        # 实测：`GetSFSymbols` 在没有符号时返回 **None**（不是缺方法），有符号时返回数组。
        # 所以 None 要当成 0，而不是 -1（上一轮误判"判据不可得"就是栽在这里）。
        for name in ("GetSurfaceFinishSymbols", "GetSFSymbols"):
            try:
                v = getattr(view, name)
            except Exception:
                continue                      # 真·不存在才跳过
            if v is None:
                return 0
            try:
                return len(list(v))
            except TypeError:
                return 0
        return -1

    # 必须先激活视图（实测：未激活时 getter 返回 None，会误判成"没有判据"）
    activated = False
    try:
        doc_w.ActivateView(val(view, "Name"))
        activated = True
    except Exception:
        pass
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
                          "activated": activated,
                          "symbols_before": before, "symbols_after": after,
                          "attempts": attempts})
    out["checks"] = {
        "call_returned_true": any(a.get("returned") == "True" for a in attempts),
        "count_available": after >= 0,
        "symbols_increased": after > before,
    }
    # 只有拿到"计数确实 +1"才算验证通过；只返回 True 不算证据
    out["ok"] = out["checks"]["symbols_increased"]
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

def _com_val(obj: Any, name: str) -> Any:
    """comtypes 下属性/方法双形态：能调就调，调不动就当属性。"""
    try:
        v = getattr(obj, name)
    except Exception:
        return None
    if not callable(v):
        return v
    try:
        return v()
    except Exception:
        return v


def _count(obj: Any, prop: str) -> int:
    """读某个集合属性的数量；拿不到返回 -1。"""
    v = val(obj, prop)
    if v is None:
        return -1
    try:
        return len(list(v))
    except TypeError:
        return -1


def aux_view(doc_w: Any) -> Dict[str, Any]:
    """辅助视图：`CreateAuxiliaryView()` 是**零参**，靠选择集驱动。

    判据：图纸视图数 +1。
    """
    out = _result("sw_add_auxiliary_view", "IDrawingDoc.CreateAuxiliaryView")
    view = first_model_view(doc_w)
    if view is None:
        out["detail"]["error"] = "图纸里没有模型视图"
        return out
    try:
        doc_w.ActivateView(val(view, "Name"))
    except Exception:
        pass
    ents = _view_entities(view, limit=6)
    before = val(doc_w, "GetViewCount", 0)
    out["detail"].update({"view": val(view, "Name"), "entities": len(ents),
                          "views_before": before})
    if not ents:
        out["detail"]["error"] = "视图里没有可用实体"
        return out
    attempts = []
    for idx in range(min(4, len(ents))):
        for mark in (1, 0):
            doc_w.ClearSelection2(True)
            try:
                ents[idx].Select2(False, mark)
            except Exception:
                continue
            try:
                res = doc_w.CreateAuxiliaryView()
            except Exception as exc:                # noqa: BLE001
                attempts.append({"idx": idx, "mark": mark, "error": str(exc)[:70]})
                continue
            after = val(doc_w, "GetViewCount", 0)
            attempts.append({"idx": idx, "mark": mark,
                             "returned": type(res).__name__ if res is not None else None,
                             "views_after": after})
            if (after or 0) > (before or 0):
                out["detail"].update({"views_after": after, "attempts": attempts[-4:]})
                out["checks"] = {"view_added": True}
                out["ok"] = True
                return out
    out["detail"].update({"views_after": val(doc_w, "GetViewCount", 0),
                          "attempts": attempts[-6:]})
    out["checks"] = {"view_added": False}
    return out


def section_view(doc_w: Any, plane_name: str = "前视基准面",
                 offset: float = 0.0) -> Dict[str, Any]:
    """剖视图：`ModelViewManager.CreateSectionViewData()` → 设 FirstPlane/FirstOffset
    → `CreateSectionView(data)`，成功后用 `RemoveSectionView()` 复位。

    判据：`CreateSectionView` 返回 True（并确认已复位）。
    """
    out = _result("sw_create_section_view", "IModelViewManager.CreateSectionView")
    sw, md = com_doc()
    try:
        mvm = md.ModelViewManager
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "ModelViewManager: %s" % str(exc)[:80]
        return out
    # 找基准面：**必须**用 comtypes 的 IFeature。pywin32 的 _Dispatch 没有可用的
    # QueryInterface（实测报 `<unknown>.QueryInterface`），传进 FirstPlane 会失败。
    plane_ct, plane_name_found = None, None
    feat = _com_val(md, "FirstFeature")
    guard = 0
    while feat is not None and guard < 500:
        guard += 1
        try:
            fc = feat.QueryInterface(sw.IFeature)
        except Exception:
            fc = feat
        try:
            type_name = _com_val(fc, "GetTypeName2")
            name = _com_val(fc, "Name")
            if type_name == "RefPlane" and plane_name in (name or ""):
                plane_ct, plane_name_found = fc, name
                break
        except Exception:
            pass
        try:
            feat = _com_val(fc, "GetNextFeature")
        except Exception:
            break
    if plane_ct is None:
        out["detail"]["error"] = "找不到基准面：%s（只用 comtypes IFeature 匹配）" % plane_name
        return out
    try:
        data = mvm.CreateSectionViewData()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "CreateSectionViewData: %s" % str(exc)[:80]
        return out
    if data is None:
        out["detail"]["error"] = "CreateSectionViewData 返回 None"
        return out
    sd = data.QueryInterface(sw.ISectionViewData)
    try:
        sd.FirstPlane = plane_ct
        sd.FirstOffset = float(offset)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["set_error"] = str(exc)[:90]
    try:
        ok = bool(mvm.CreateSectionView(sd))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "CreateSectionView: %s" % str(exc)[:90]
        return out
    removed = None
    if ok:
        try:
            mvm.RemoveSectionView()
            removed = True
        except Exception:
            removed = False
    out["detail"].update({"plane": plane_name_found, "offset": float(offset),
                          "returned": ok, "removed": removed})
    out["checks"] = {"section_view_created": ok}
    out["ok"] = ok
    return out


def broken_view(view: Any, orientation: int = 0, position: float = 0.05,
                size: float = 0.01) -> Dict[str, Any]:
    """断裂视图：`IView.InsertBreak2(5 参)`。

    **关键判据**：断裂视图**不新增视图**——必须看 `GetBreakLines` 数量（原审计看视图数，
    所以永远判失败）。
    """
    out = _result("sw_add_broken_view", "IView.InsertBreak2")
    if view is None:
        out["detail"]["error"] = "没有模型视图"
        return out
    before = _count(view, "GetBreakLines")
    try:
        res = view.InsertBreak2(int(orientation), float(position), float(size), 0, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "InsertBreak2: %s" % str(exc)[:100]
        return out
    after = _count(view, "GetBreakLines")
    out["detail"].update({"view": val(view, "Name"), "break_lines_before": before,
                          "break_lines_after": after, "returned": str(res)})
    out["checks"] = {"break_lines_increased": after > before}
    out["ok"] = out["checks"]["break_lines_increased"]
    return out


def drawing_dimension(doc_w: Any, x: float = 0.12, y: float = 0.12) -> Dict[str, Any]:
    """图纸尺寸：选视图里两条边（mark=1）→ `AddDimension2(x,y,0)`。

    判据：`IView.GetDisplayDimensions` 计数 +1。
    """
    out = _result("sw_add_drawing_dimension", "IModelDoc2.AddDimension2")
    view = first_model_view(doc_w)
    if view is None:
        out["detail"]["error"] = "图纸里没有模型视图"
        return out
    ents = _view_entities(view, limit=5)
    before = _count(view, "GetDisplayDimensions")
    out["detail"].update({"view": val(view, "Name"), "entities": len(ents),
                          "dimensions_before": before})
    if len(ents) < 2:
        out["detail"]["error"] = "可用实体不足两条"
        return out
    _sw, md = com_doc()
    attempts = []
    for i in range(min(4, len(ents))):
        for j in range(i + 1, min(5, len(ents))):
            for mark in (1, 0):
                doc_w.ClearSelection2(True)
                try:
                    ents[i].Select2(False, mark)
                    ents[j].Select2(True, mark)
                except Exception:
                    continue
                try:
                    res = md.AddDimension2(float(x), float(y), 0.0)
                except Exception as exc:            # noqa: BLE001
                    attempts.append({"pair": [i, j], "mark": mark,
                                     "error": str(exc)[:60]})
                    continue
                after = _count(view, "GetDisplayDimensions")
                attempts.append({"pair": [i, j], "mark": mark,
                                 "returned": type(res).__name__ if res is not None else None,
                                 "dimensions_after": after})
                if after > before:
                    out["detail"].update({"dimensions_after": after,
                                          "attempts": attempts[-6:]})
                    out["checks"] = {"dimensions_increased": True}
                    out["ok"] = True
                    return out
    out["detail"].update({"dimensions_after": _count(view, "GetDisplayDimensions"),
                          "attempts": attempts[-8:]})
    out["checks"] = {"dimensions_increased": False}
    return out


def hole_table(doc_w: Any, x: float = 0.10, y: float = 0.16) -> Dict[str, Any]:
    """孔表：`IView.InsertHoleTable2(UseAnchor, X, Y, AnchorType, Template, OriginMarker)`。

    两个前提（都踩过）：

    1. 必须先 `ActivateView`，否则 `InsertHoleTable2` 返回 None；
    2. 视图方向要能看到孔（前视/后视/等轴测；上视不行）。

    判据：图纸上 `*Table*` 类特征数 +1。
    """
    from ..core.com import val as _val
    from ._common import iter_features
    out = _result("sw_add_hole_table", "IView.InsertHoleTable2")
    view = first_model_view(doc_w)
    if view is None:
        out["detail"]["error"] = "图纸里没有模型视图"
        return out

    def n_tables() -> int:
        n = 0
        for feat in iter_features(doc_w):
            if "Table" in (_val(feat, "GetTypeName2") or ""):
                n += 1
        return n

    before = n_tables()
    try:
        doc_w.ActivateView(_val(view, "Name"))
        activated = True
    except Exception:
        activated = False
    ents = _view_entities(view)
    circles = []
    for ee in ents:
        try:
            p = [float(v) for v in list(_val(ee, "GetCurveParams2") or [])]
            if len(p) >= 6 and sum((p[3 + i] - p[i]) ** 2 for i in range(3)) ** 0.5 < 1e-9:
                circles.append(ee)
        except Exception:
            continue
    out["detail"].update({"view": _val(view, "Name"), "activated": activated,
                          "entities": len(ents), "circles": len(circles),
                          "tables_before": before})
    attempts = []
    picks = ([circles[0]] if circles else []) + [None]
    for pick in picks:
        for anchor in (1, 0):
            doc_w.ClearSelection2(True)
            if pick is not None:
                try:
                    pick.Select2(False, 1)
                except Exception:
                    pass
            try:
                res = view.InsertHoleTable2(True, float(x), float(y), anchor, "", "")
            except Exception as exc:                # noqa: BLE001
                attempts.append({"pick": pick is not None, "anchor": anchor,
                                 "error": str(exc)[:70]})
                continue
            after = n_tables()
            attempts.append({"pick": pick is not None, "anchor": anchor,
                             "returned": type(res).__name__ if res is not None else None,
                             "tables_after": after})
            if after > before:
                out["detail"].update({"tables_after": after, "attempts": attempts[-6:]})
                out["checks"] = {"table_added": True}
                out["ok"] = True
                return out
    out["detail"].update({"tables_after": n_tables(), "attempts": attempts[-8:]})
    out["checks"] = {"table_added": False}
    return out