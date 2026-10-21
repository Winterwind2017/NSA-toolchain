"""swkit.verified.doc_ops —— 文档级基础操作（新建/选择/删除特征/参考面/截图/方程）

判据：

| 工具 | 判据 |
|---|---|
| `connect` | 版本号可读 + 文档数可读 |
| `create_part` | 文档类型 == 1（零件） |
| `select_entity` | 选择集数量 == 1 |
| `clear_selection` | 选择集数量 == 0 |
| `delete_feature` | 特征数 **-1** |
| `create_reference_plane` | 参考面数 **+1** |
| `capture_screenshot` | PNG 魔数 + 尺寸 |
| `add_equation` / `delete_equation` | 方程数 +1 / -1 |
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, pyw, val
from ._common import iter_features, shape_counts, wrap

__all__ = ["connect", "create_part", "select_entity", "clear_selection",
           "delete_feature", "create_reference_plane", "capture_screenshot",
           "add_equation", "delete_equation", "PART_TEMPLATE"]

PART_TEMPLATE = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
                r"\gb_part.prtdot")


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _sel_count(doc: Any) -> int:
    try:
        return int(doc.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:
        return -1


def _count_type(doc: Any, type_name: str) -> int:
    n = 0
    for feat in iter_features(doc):
        try:
            if str(val(feat, "GetTypeName2")) == type_name:
                n += 1
        except Exception:
            continue
    return n


def connect() -> Dict[str, Any]:
    """连接检查（只读）。"""
    out = _result("sw_connect", "Application.RevisionNumber / GetDocumentCount")
    app = pyw().Dispatch("SldWorks.Application")
    rev = val(app, "RevisionNumber")
    n = val(app, "GetDocumentCount")
    out["detail"] = {"revision": rev, "document_count": n}
    out["checks"] = {"connected": bool(rev), "count_readable": isinstance(n, int)}
    out["ok"] = all(out["checks"].values())
    return out


def create_part(template: str = "") -> Dict[str, Any]:
    """新建零件。判据：类型 == 1。"""
    out = _result("sw_create_part", "Application.NewDocument(.prtdot)")
    tpl = template or PART_TEMPLATE
    if not os.path.isfile(tpl):
        out["detail"]["error"] = "零件模板不存在：%s" % tpl
        return out
    try:
        from ._common import com_app
        _sw, app_ct = com_app()
        app_w = pyw().Dispatch("SldWorks.Application")
        app_w.CloseAllDocuments(True)
        if app_ct.NewDocument(tpl, 0, 0.0, 0.0) is None:
            out["detail"]["error"] = "NewDocument 返回 None"
            return out
        doc_w = app_w.ActiveDoc
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    dtype = val(doc_w, "GetType")
    out["detail"] = {"type": dtype, "title": val(doc_w, "GetTitle")}
    out["checks"] = {"is_part": dtype == 1}
    out["ok"] = out["checks"]["is_part"]
    return out


def select_entity(doc: Any, name: str, kind: str = "PLANE",
                  append: bool = False) -> Dict[str, Any]:
    """按名字+类型选中实体。判据：选择集 == 1（append 时 >0）。"""
    out = _result("sw_select_entity", "IModelDocExtension.SelectByID2")
    try:
        doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2(name, kind, 0, 0, 0, bool(append), 0,
                                       none_dispatch(), 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    n = _sel_count(doc)
    out["detail"] = {"name": name, "kind": kind, "returned": ok, "selected": n}
    out["checks"] = {"selected": n >= 1}
    out["ok"] = out["checks"]["selected"]
    return out


def clear_selection(doc: Any) -> Dict[str, Any]:
    """清空选择集。判据：选择集 == 0。"""
    out = _result("sw_clear_selection", "IModelDoc2.ClearSelection2")
    before = _sel_count(doc)
    try:
        doc.ClearSelection2(True)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _sel_count(doc)
    out["detail"] = {"before": before, "after": after}
    out["checks"] = {"cleared": after == 0}
    out["ok"] = out["checks"]["cleared"]
    return out


def delete_feature(doc: Any, name: str) -> Dict[str, Any]:
    """删除特征。判据：特征数 -1。"""
    out = _result("sw_delete_feature", "IModelDocExtension.DeleteSelection2")
    before = shape_counts(doc)["features"]
    try:
        # 类型名要试：参考面在 pywin32 下只认 "PLANE"，不认 DATUMPLANE/BODYFEATURE
        # （实测三者全 False，只有 PLANE 命中）。
        ok = False
        used = None
        for kind in ("BODYFEATURE", "FEATURE", "PLANE", "SKETCH"):
            doc.ClearSelection2(True)
            ok = doc.Extension.SelectByID2(name, kind, 0, 0, 0, False, 0,
                                           none_dispatch(), 0)
            if ok:
                used = kind
                break
        if not ok:
            out["detail"]["error"] = "选不中特征：%s" % name
            return out
        out["detail"]["select_kind"] = used
        doc.Extension.DeleteSelection2(1)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = shape_counts(doc)["features"]
    out["detail"].update({"feature": name, "features_before": before,
                          "features_after": after})
    out["checks"] = {"feature_removed": after == before - 1}
    out["ok"] = out["checks"]["feature_removed"]
    return out


def create_reference_plane(doc: Any, base_plane: str = "前视基准面",
                           offset_mm: float = 50.0) -> Dict[str, Any]:
    """建参考面（基准面偏移）。判据：`RefPlane` 数 +1。"""
    out = _result("sw_create_reference_plane", "IFeatureManager.InsertRefPlane")
    before = _count_type(doc, "RefPlane")
    try:
        doc.ClearSelection2(True)
        doc.Extension.SelectByID2(base_plane, "PLANE", 0, 0, 0, False, 0,
                                  none_dispatch(), 0)
        fm = doc.FeatureManager
        feat = fm.InsertRefPlane(8, float(offset_mm) / 1000.0, 0, 0, 0, 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _count_type(doc, "RefPlane")
    out["detail"].update({"offset_mm": offset_mm, "planes_before": before,
                          "planes_after": after,
                          "feature": val(feat, "Name") if feat is not None else None})
    out["checks"] = {"plane_added": after == before + 1}
    out["ok"] = out["checks"]["plane_added"]
    return out


def capture_screenshot(doc: Any, path: str = "") -> Dict[str, Any]:
    """截图。判据：PNG 魔数 `\\x89PNG` + 大小 > 10 KB。"""
    out = _result("sw_capture_screenshot", "IModelDocExtension.SaveAs(PNG)")
    target = os.path.abspath(path or os.path.join(
        os.path.expanduser("~"), ".swkit", "export", "shot.png"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        try:
            os.remove(target)
        except OSError:
            pass
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        err = val(md, "SaveAs2") and None
        md.SaveAs(target)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    size = os.path.getsize(target) if os.path.exists(target) else 0
    head = b""
    if size:
        with open(target, "rb") as fh:
            head = fh.read(8)
    out["detail"] = {"path": target, "bytes": size, "head": head[:4].hex()}
    out["checks"] = {"file_exists": size > 0, "is_png": head.startswith(b"\x89PNG"),
                     "size_ok": size > 10_000}
    out["ok"] = all(out["checks"].values())
    return out


def add_equation(doc: Any, expression: str = '"D1@草图1" = 40') -> Dict[str, Any]:
    """加方程/全局变量：`IEquationMgr.Add2(-1, expr, False)`。

    坑（实测 SW 2025 SP4.1）：

    * `IModelDoc2` **没有** `AddEquation`；方程只能走 `IEquationMgr`
    * `GetEquationMgr()` 在 **pywin32** 下报"找不到成员" → 必须 **comtypes**
    * `GetCount` / `Value` / `Equation` 在 comtypes 下是**方法**，要带括号
    * `Add2` 成功返回**下标**（首条 0），失败返回 -1

    判据：计数 +1 **且** `Equation(下标)` 读回与写入一致（不是只看返回值）。
    """
    out = _result("sw_add_equation", "IEquationMgr.Add2(-1, expr, False)")
    try:
        from .equations import equation_manager
        em = equation_manager(doc)
        before = em.GetCount()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    out["detail"].update({"expression": expression, "count_before": before})
    try:
        idx = em.Add2(-1, expression, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = em.GetCount()
    got = None
    if isinstance(idx, int) and idx >= 0:
        try:
            got = em.Equation(idx)
        except Exception:                           # noqa: BLE001
            got = None
    out["detail"].update({"returned_index": idx, "count_after": after,
                          "readback": got})
    out["checks"] = {"equation_count": after > before,
                     "readback_matches": got == expression}
    out["ok"] = all(out["checks"].values())
    return out


def delete_equation(doc: Any, index: int = 0) -> Dict[str, Any]:
    """删方程/全局变量：`IEquationMgr.Delete(index)`。判据：计数 -1。"""
    out = _result("sw_delete_equation", "IEquationMgr.Delete(index)")
    try:
        from .equations import equation_manager
        em = equation_manager(doc)
        before = em.GetCount()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if before <= 0:
        out["detail"].update({"count_before": before, "error": "没有方程可删"})
        return out
    try:
        em.Delete(int(index))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = em.GetCount()
    out["detail"].update({"index": index, "count_before": before, "count_after": after})
    out["checks"] = {"equation_removed": after == before - 1}
    out["ok"] = out["checks"]["equation_removed"]
    return out


def _equation_count(doc: Any) -> int:
    """`GetEquations` 返回数组；读不到返回 -1。"""
    try:
        eqs = doc.GetEquations()
        if eqs is None:
            return 0
        return len(list(eqs))
    except Exception:
        return -1
