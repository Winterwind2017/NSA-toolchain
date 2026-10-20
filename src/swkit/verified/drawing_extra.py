"""swkit.verified.drawing_extra —— 图纸补充能力（修订表 / 详图 / 旋转 / 导出）

判据：

| 工具 | 判据 |
|---|---|
| `add_revision_table` | 图纸表格数 **+1** |
| `add_detail_view` | 视图数 **+1**（`CreateDetailViewAt3` 9 参） |
| `view_rotate` | `IView.Angle` 读回变化 |
| `export_pdf` | 文件头 `%PDF`（图纸导出与零件 DXF 不同，是可靠的） |
| `export_dwg` | 文件存在 + DWG 魔数 `AC10` |

实测要点：
* `ISheet.InsertRevisionTable2` 是 **7 参**（UseAnchorPoint, X, Y, AnchorType,
  TableTemplate, Shape, AutoUpdateZoomCells）；`InsertRevisionTable` 是 5 参。
* `CreateDetailViewAt3` 是 **9 参**（X, Y, Z, Style, Scale1, Scale2, LabelIn,
  Showtype, FullOutline）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, pyw, val

__all__ = ["add_revision_table", "add_detail_view", "view_rotate",
           "export_pdf", "export_dwg", "table_count", "view_count",
           "add_drawing_view", "add_section_view", "add_bom_table"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _sheet(doc: Any) -> Any:
    return pyw().Dispatch(doc.GetCurrentSheet())


def view_count(doc: Any) -> int:
    try:
        return int(val(doc, "GetViewCount"))
    except Exception:
        return -1


def revision_table(doc: Any) -> Any:
    """当前图纸的修订表对象（没有则 None）。

    `ISheet.GetFirstTableAnnotation` 在本机 pywin32 下取不到（报"找不到成员"），
    改用 `ISheet.RevisionTable`（0 参属性）——它本身就是最直接的判据。
    """
    try:
        return _sheet(doc).RevisionTable
    except Exception:
        return None


def table_count(doc: Any) -> int:
    """图纸上"有没有修订表"（1/0），读不到返回 -1。"""
    try:
        tbl = revision_table(doc)
        return 0 if tbl is None else 1
    except Exception:
        return -1


def add_revision_table(doc: Any, x_mm: float = 10.0, y_mm: float = 10.0,
                       template: str = "") -> Dict[str, Any]:
    """插入修订表。判据：表格数 +1。"""
    out = _result("sw_add_revision_table", "ISheet.InsertRevisionTable2(7 参)")
    before = table_count(doc)
    out["detail"].update({"tables_before": before})
    try:
        # pywin32 的动态对象上 `InsertRevisionTable2` 报"找不到成员"，
        # 必须走 comtypes 强类型 `ISheet`。
        from ._common import com_doc
        _sw, md = com_doc()
        # `GetCurrentSheet` 在 **IDrawingDoc** 上，不在 IModelDoc2 上（实测
        # 直接调 md.GetCurrentSheet 报 AttributeError）。
        dd = md.QueryInterface(_sw.IDrawingDoc)
        sheet_ct = dd.GetCurrentSheet()
        ok = sheet_ct.InsertRevisionTable2(False, float(x_mm) / 1000.0,
                                           float(y_mm) / 1000.0, 0,
                                           template or "", 0, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = table_count(doc)
    out["detail"].update({"tables_after": after, "returned": ok})
    out["checks"] = {"table_added": after > before}
    out["ok"] = out["checks"]["table_added"]
    return out


def add_detail_view(doc: Any, x_mm: float = 100.0, y_mm: float = 100.0,
                    scale: float = 2.0, label: str = "A") -> Dict[str, Any]:
    """插入详图。判据：视图数 +1。"""
    out = _result("sw_add_detail_view", "IDrawingDoc.CreateDetailViewAt3(9 参)")
    before = view_count(doc)
    out["detail"].update({"views_before": before, "scale": scale, "label": label})
    try:
        from .drawing import first_model_view
        parent = first_model_view(doc)
        if parent is not None:
            doc.ClearSelection2(True)
            doc.Extension.SelectByID2(val(parent, "GetName2"), "DRAWINGVIEW",
                                      0, 0, 0, False, 0, none_dispatch(), 0)
        view = doc.CreateDetailViewAt3(float(x_mm) / 1000.0, float(y_mm) / 1000.0,
                                      0.0, 0, float(scale), float(scale),
                                      label, 0, True)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = view_count(doc)
    out["detail"].update({"views_after": after,
                          "view": val(view, "GetName2") if view is not None else None})
    out["checks"] = {"view_added": after > before}
    out["ok"] = out["checks"]["view_added"]
    return out


def view_rotate(doc: Any, angle_deg: float = 15.0, view_index: int = 0) -> Dict[str, Any]:
    """旋转视图。判据：`IView.Angle` 读回变化。"""
    out = _result("sw_view_rotate", "IDrawingDoc.DrawingViewRotate")
    from .drawing import first_model_view
    # `IModelDoc2.GetViews` 在 pywin32 下不存在（报"没有视图"），改用已验证的
    # `first_model_view()`（按 Type != 1 找模型视图）。
    view = first_model_view(doc)
    if view is None:
        out["detail"]["error"] = "图纸上没有模型视图"
        return out
    before = val(view, "Angle")
    out["detail"].update({"view": val(view, "GetName2"), "angle_before_deg": before})
    try:
        name = val(view, "GetName2")
        doc.ClearSelection2(True)
        doc.Extension.SelectByID2(name, "DRAWINGVIEW", 0, 0, 0, False, 0,
                                  none_dispatch(), 0)
        doc.DrawingViewRotate(float(angle_deg))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = val(view, "Angle")
    out["detail"]["angle_after_deg"] = after
    out["checks"] = {"angle_changed": before is not None and after is not None
                     and abs(float(after) - float(before)) > 1e-9}
    out["ok"] = out["checks"]["angle_changed"]
    return out


def _sig(path: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"bytes": 0}
    try:
        info["bytes"] = os.path.getsize(path)
        with open(path, "rb") as fh:
            head = fh.read(32)
    except OSError as exc:
        info["error"] = str(exc)
        return info
    info["head"] = head[:8].decode("latin-1", "replace")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        info["format_ok"] = head.startswith(b"%PDF")
    elif ext in (".dwg", ".dxf"):
        info["format_ok"] = head.startswith(b"AC10") or b"SECTION" in head
    else:
        info["format_ok"] = True
    return info


def _export(tool: str, api: str, path: str) -> Dict[str, Any]:
    out = _result(tool, api)
    target = os.path.abspath(path)
    if os.path.exists(target):
        try:
            os.remove(target)
        except OSError as exc:
            out["detail"]["error"] = "旧文件删不掉：%s" % exc
            return out
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        md.SaveAs(target)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    info = _sig(target)
    out["detail"].update({"path": target, **info})
    out["checks"] = {"file_exists": info.get("bytes", 0) > 0,
                     "signature_ok": bool(info.get("format_ok"))}
    out["ok"] = all(out["checks"].values())
    return out


def export_pdf(doc: Any, path: str) -> Dict[str, Any]:
    """图纸导出 PDF。判据：`%PDF`。"""
    return _export("sw_export_drawing_pdf", "IModelDoc2.SaveAs(PDF)", path)


def export_dwg(doc: Any, path: str) -> Dict[str, Any]:
    """图纸导出 DWG/DXF。判据：`AC10` 或 `SECTION`。"""
    return _export("sw_export_drawing_dwg", "IModelDoc2.SaveAs(DWG)", path)

def add_drawing_view(doc: Any, model_path: str, view_name: str = "top",
                     x: float = 0.25, y: float = 0.15) -> Dict[str, Any]:
    """从模型再加一个视图。判据：视图数 +1。"""
    out = _result("sw_add_drawing_view",
                  "IModelDocExtension.CreateDrawViewFromModelView3")
    before = view_count(doc)
    out["detail"].update({"view_name": view_name, "views_before": before,
                          "model": model_path})
    try:
        # 该 API 在 **IDrawingDoc** 上（不在 Extension 上，两处都试过才定位到），
        # 且中文版只认本地化视图名（*前视 / *上视 …）。
        from ._common import com_doc
        from .drawing import VIEW_MAP
        _sw, md = com_doc()
        dd = md.QueryInterface(_sw.IDrawingDoc)
        localized = VIEW_MAP.get(str(view_name).lower(), view_name)
        view = dd.CreateDrawViewFromModelView3(
            model_path, localized, float(x), float(y), 0.0)
        out["detail"]["localized_view"] = localized
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = view_count(doc)
    out["detail"].update({"views_after": after,
                          "view": val(view, "GetName2") if view is not None else None})
    out["checks"] = {"view_added": after > before}
    out["ok"] = out["checks"]["view_added"]
    return out


def add_section_view(doc: Any) -> Dict[str, Any]:
    """剖视图（复用已验证的 drawing.section_view）。判据：视图数 +1。"""
    out = _result("sw_add_section_view", "IDrawingDoc.CreateSectionViewAt")
    before = view_count(doc)
    out["detail"]["views_before"] = before
    try:
        from .drawing import section_view
        res = section_view(doc)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = view_count(doc)
    out["detail"].update({"views_after": after, "inner_ok": res.get("ok"),
                          "inner_error": (res.get("detail") or {}).get("error")})
    out["checks"] = {"view_added": after > before}
    out["ok"] = out["checks"]["view_added"]
    return out


def add_bom_table(doc: Any, x: float = 0.10, y: float = 0.16) -> Dict[str, Any]:
    """插 BOM 表（需装配图）。判据：`GetBomTable` 非空。

    BomType=0 是无效值（实测直接返回 None），必须 1/2/3。
    """
    out = _result("sw_add_bom_table", "IView.InsertBomTable2(7 参)")
    view = None
    try:
        from .drawing import first_model_view
        view = first_model_view(doc)
    except Exception:
        view = None
    if view is None:
        out["detail"]["error"] = "图纸上没有模型视图"
        return out
    bom = None
    attempts = []
    try:
        bom = view.GetBomTable()
        if callable(bom):
            bom = bom()
    except Exception:
        bom = None
    if bom is None:
        for bom_type in (1, 2, 3):
            try:
                bom = view.InsertBomTable2(True, float(x), float(y), 1,
                                           bom_type, "", "")
            except Exception as exc:                # noqa: BLE001
                attempts.append({"bom_type": bom_type, "error": str(exc)[:60]})
                continue
            attempts.append({"bom_type": bom_type,
                             "returned": type(bom).__name__ if bom is not None else None})
            if bom is not None:
                break
    out["detail"].update({"attempts": attempts, "bom_present": bom is not None})
    out["checks"] = {"bom_table_created": bom is not None}
    out["ok"] = out["checks"]["bom_table_created"]
    if not out["ok"]:
        out["detail"]["error"] = "InsertBomTable2 未能建表（需装配图）"
    return out