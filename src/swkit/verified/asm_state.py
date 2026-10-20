"""swkit.verified.asm_state —— 装配结构与组件状态（建/插/树/抑制/隐藏/替换）

判据全是**状态位或计数**，不看返回值：

| 工具 | 判据 |
|---|---|
| `create_assembly` | `GetType == 2`（装配体） |
| `insert_component` | 组件数 +1，且路径读回一致 |
| `assembly_tree` | 组件数与 `GetComponents` 一致，状态位可读 |
| `suppress_component` | `IComponent2.IsSuppressed` 读回等于目标 |
| `hide_component` | `IComponent2.IsHidden(False)` 读回等于目标 |
| `replace_component` | 组件 `GetPathName` 读回**含新文件名** |

实测坑：
* `IComponent2.IsHidden` 需要 1 个参数（`ConsiderSuppressed`），不能用无参 `val()`；
* 抑制要用 `IAssemblyDoc.SetComponentSuppression(2/0)`，不是 `IFeature.SetSuppression2`；
* `ReplaceComponents2` 是 **5 参**（FileName, ConfigName, ReplaceAllInstance,
  UseConfigChoice, ReAttachMates），少传会被拒。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import pyw, val
from ._common import com_app, com_doc, wrap

__all__ = ["create_assembly", "insert_component", "assembly_tree", "suppress_component",
           "hide_component", "replace_component", "suppress_feature",
           "unsuppress_feature", "ORIGIN_MARK"]

ORIGIN_MARK = 0
DEFAULT_TEMPLATE = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
                   r"\gb_assembly.asmdot")


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _activate(asm_doc: Any) -> bool:
    """把装配激活成 ActiveDoc。

    必要性：`com_doc()` 取的是 ActiveDoc，而 `AddComponent5` 要求零件已打开
    （一打开零件，ActiveDoc 就变成零件了）→ 必须先激活回来。
    """
    title = val(asm_doc, "GetTitle")
    if not title:
        return False
    app_w = pyw().Dispatch("SldWorks.Application")
    # 实测：`ActivateDoc(title)` 单参版可用；`ActivateDoc2/3` 报"类型不匹配"
    # （末尾的 byref 参数在 pywin32 下过不去）。
    for call in (lambda: app_w.ActivateDoc(title),
                 lambda: app_w.ActivateDoc2(title, False, 0),
                 lambda: app_w.ActivateDoc3(title, False, 0, 0)):
        try:
            call()
            if str(val(app_w.ActiveDoc, "GetTitle") or "") == str(title):
                return True
        except Exception:
            continue
    return False


def _act(obj: Any, name: str, *args) -> Any:
    """属性/方法双形态：能调就调，调不动就当属性（读取即生效）。"""
    try:
        v = getattr(obj, name)
    except Exception:
        return None
    if not callable(v):
        return v
    try:
        return v(*args)
    except TypeError:
        return v


def _components(asm_doc: Any) -> List[Any]:
    try:
        return [wrap(c) for c in (asm_doc.GetComponents(False) or [])]
    except Exception:
        return []


def _find_component(asm_doc: Any, name: str) -> Optional[Any]:
    """按名字（或前缀）找组件。"""
    comps = _components(asm_doc)
    for c in comps:
        nm = val(c, "Name2") or val(c, "Name")
        if nm and (nm == name or str(nm).startswith(name)):
            return c
    return None


def _is_hidden(comp: Any) -> Optional[bool]:
    try:
        return bool(comp.IsHidden(False))     # 必须传 ConsiderSuppressed
    except Exception:
        return None


def _feature_suppressed(feat: Any) -> Optional[bool]:
    """判据只用 `IsSuppressed`（0 参属性）。

    实测：`IsSuppressed2(0, None)` 读回 **None**（不可用），不能当判据。
    """
    try:
        v = feat.IsSuppressed
        return bool(v) if isinstance(v, bool) else None
    except Exception:
        return None


def _is_suppressed(comp: Any) -> Optional[bool]:
    v = val(comp, "IsSuppressed")
    return bool(v) if isinstance(v, bool) else None


def create_assembly(template: str = "") -> Dict[str, Any]:
    """新建装配文档。判据：文档类型 == 2。"""
    out = _result("sw_create_assembly", "Application.NewDocument(.asmdot)")
    tpl = template or DEFAULT_TEMPLATE
    if not os.path.isfile(tpl):
        out["detail"]["error"] = "装配模板不存在：%s" % tpl
        return out
    _sw, app = com_app()
    # 用 pywin32 的 Application 取 ActiveDoc：comtypes 的 `app.ActiveDoc` 返回的是
    # POINTER(IAssemblyDoc)，`pyw().Dispatch(pointer)` 会失败 → 后续读数全是 None。
    app_w = pyw().Dispatch("SldWorks.Application")
    app_w.CloseAllDocuments(True)
    doc = app.NewDocument(tpl, 0, 0.0, 0.0)
    if isinstance(doc, tuple):
        doc = doc[-1]
    if doc is None:
        out["detail"]["error"] = "NewDocument 失败"
        return out
    doc_w = app_w.ActiveDoc
    dtype = val(doc_w, "GetType")
    out["detail"].update({"template": os.path.basename(tpl), "type": dtype,
                          "title": val(doc_w, "GetTitle")})
    out["checks"] = {"is_assembly": dtype == 2}
    out["ok"] = out["checks"]["is_assembly"]
    return out


def insert_component(asm_doc: Any, part_path: str, x_mm: float = 0.0,
                     y_mm: float = 0.0, z_mm: float = 0.0,
                     fixed: bool = False) -> Dict[str, Any]:
    """插入组件（`AddComponent5` 8 参）。判据：组件数 +1 且路径读回一致。"""
    out = _result("sw_insert_component", "IAssemblyDoc.AddComponent5")
    activated = _activate(asm_doc)
    before = len(_components(asm_doc))
    path = os.path.abspath(part_path)
    out["detail"].update({"part": os.path.basename(path), "components_before": before,
                          "assembly_activated": activated})
    if not os.path.isfile(path):
        out["detail"]["error"] = "零件不存在：%s" % path
        return out
    try:
        _sw, md = com_doc()
        asm_ct = md.QueryInterface(_sw.IAssemblyDoc)
        comp = asm_ct.AddComponent5(path, 0, "", bool(fixed), "",
                                    float(x_mm) / 1000.0, float(y_mm) / 1000.0,
                                    float(z_mm) / 1000.0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _components(asm_doc)
    out["detail"]["components_after"] = len(after)
    if comp is None:
        out["detail"]["note"] = "AddComponent5 返回 None（零件未预先打开时会这样）"
    out["checks"] = {"count_increased": len(after) == before + 1}
    out["ok"] = out["checks"]["count_increased"]
    return out


def assembly_tree(asm_doc: Any) -> Dict[str, Any]:
    """装配树：名称 / 路径 / 是否固定 / 是否抑制 / 是否隐藏。"""
    out = _result("sw_get_assembly_tree", "IAssemblyDoc.GetComponents + 状态位")
    comps = _components(asm_doc)
    rows = []
    for c in comps:
        rows.append({
            "name": val(c, "Name2") or val(c, "Name"),
            "path": val(c, "GetPathName"),
            "fixed": bool(val(c, "IsFixed", False)),
            "suppressed": _is_suppressed(c),
            "hidden": _is_hidden(c),
        })
    out["detail"] = {"count": len(rows), "components": rows}
    out["checks"] = {"has_components": len(rows) > 0,
                     "states_readable": all(r["suppressed"] is not None for r in rows)}
    out["ok"] = out["checks"]["has_components"] and out["checks"]["states_readable"]
    return out


def suppress_component(asm_doc: Any, name: str, suppress: bool = True) -> Dict[str, Any]:
    """抑制/解除抑制组件。判据：`IsSuppressed` 读回等于目标。"""
    out = _result("sw_suppress_component", "IAssemblyDoc.SetComponentSuppression")
    comp = _find_component(asm_doc, name)
    if comp is None:
        out["detail"]["error"] = "找不到组件：%s" % name
        return out
    out["detail"].update({"component": val(comp, "Name2") or name,
                          "before": _is_suppressed(comp), "target": suppress})
    try:
        _activate(asm_doc)
        asm_doc.ClearSelection2(True)
        comp.Select2(False, ORIGIN_MARK)
        try:
            out["detail"]["selected"] = asm_doc.SelectionManager.GetSelectedObjectCount2(-1)
        except Exception:
            pass
        # swComponentSuppressionState_e：0 = Suppressed，2 = Resolved。
        asm_doc.SetComponentSuppression(0 if suppress else 2)
        after = _is_suppressed(comp)
        if after != suppress:                       # 退回菜单式抑制/解除
            asm_doc.ClearSelection2(True)
            comp.Select2(False, ORIGIN_MARK)
            _act(asm_doc, "EditSuppress2" if suppress else "EditUnsuppress2")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _is_suppressed(comp)
    out["detail"]["after"] = after
    out["checks"] = {"state_matches": after == suppress}
    out["ok"] = out["checks"]["state_matches"]
    return out


def hide_component(asm_doc: Any, name: str, hide: bool = True) -> Dict[str, Any]:
    """隐藏/显示组件（`IComponent2.Visible` 属性）。判据：`IsHidden(False)` 读回。"""
    out = _result("sw_hide_component", "IComponent2.Visible（属性）")
    comp = _find_component(asm_doc, name)
    if comp is None:
        out["detail"]["error"] = "找不到组件：%s" % name
        return out
    out["detail"].update({"component": val(comp, "Name2") or name,
                          "before_hidden": _is_hidden(comp), "target_hide": hide})
    try:
        _activate(asm_doc)
        asm_doc.ClearSelection2(True)
        comp.Select2(False, ORIGIN_MARK)
        # 实测：直接写 `Visible` 不改 `IsHidden`；要用 IAssemblyDoc 的
        # HideComponent / ShowComponent（0 参、作用于选择集）。
        _act(asm_doc, "HideComponent" if hide else "ShowComponent")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _is_hidden(comp)
    out["detail"]["after_hidden"] = after
    out["checks"] = {"state_matches": after == hide}
    out["ok"] = out["checks"]["state_matches"]
    return out


def replace_component(asm_doc: Any, name: str, new_path: str,
                      replace_all: bool = True) -> Dict[str, Any]:
    """替换组件（`ReplaceComponents2` 5 参）。判据：`GetPathName` 含新文件名。"""
    out = _result("sw_replace_component", "IAssemblyDoc.ReplaceComponents2")
    comp = _find_component(asm_doc, name)
    if comp is None:
        out["detail"]["error"] = "找不到组件：%s" % name
        return out
    path = os.path.abspath(new_path)
    if not os.path.isfile(path):
        out["detail"]["error"] = "新文件不存在：%s" % path
        return out
    before = val(comp, "GetPathName")
    out["detail"].update({"component": val(comp, "Name2") or name,
                          "before_path": before,
                          "target": os.path.basename(path)})
    try:
        _activate(asm_doc)
        asm_doc.ClearSelection2(True)
        comp.Select2(False, ORIGIN_MARK)
        _sw, md = com_doc()
        asm_ct = md.QueryInterface(_sw.IAssemblyDoc)
        asm_ct.ReplaceComponents2(path, "", bool(replace_all), True, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    comp2 = _find_component(asm_doc, name) or comp
    after = val(comp2, "GetPathName")
    out["detail"]["after_path"] = after
    out["checks"] = {"path_changed": str(after or "").lower().endswith(
        os.path.basename(path).lower())}
    out["ok"] = out["checks"]["path_changed"]
    return out


def suppress_feature(doc: Any, feature_name: str) -> Dict[str, Any]:
    """抑制特征（`EditSuppress2`）。判据：`IsSuppressed2` 读回 True。"""
    out = _result("sw_suppress_feature", "IModelDoc2.EditSuppress2")
    feat = None
    try:
        feat = doc.FeatureByName(feature_name)
    except Exception:
        feat = None
    if feat is None:
        out["detail"]["error"] = "找不到特征：%s" % feature_name
        return out
    feat = wrap(feat)
    before = _feature_suppressed(feat)
    try:
        doc.ClearSelection2(True)
        feat.Select2(False, ORIGIN_MARK)
        _act(doc, "EditSuppress2")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _feature_suppressed(feat)
    out["detail"].update({"feature": feature_name, "before": before, "after": after})
    out["checks"] = {"suppressed": after is True}
    out["ok"] = out["checks"]["suppressed"]
    return out


def unsuppress_feature(doc: Any, feature_name: str) -> Dict[str, Any]:
    """解除抑制（`EditUnsuppress2`）。判据：`IsSuppressed2` 读回 False。"""
    out = _result("sw_unsuppress_feature", "IModelDoc2.EditUnsuppress2")
    try:
        feat = doc.FeatureByName(feature_name)
    except Exception:
        feat = None
    if feat is None:
        out["detail"]["error"] = "找不到特征：%s" % feature_name
        return out
    feat = wrap(feat)
    try:
        doc.ClearSelection2(True)
        feat.Select2(False, ORIGIN_MARK)
        _act(doc, "EditUnsuppress2")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _feature_suppressed(feat)
    out["detail"].update({"feature": feature_name, "after": after})
    out["checks"] = {"unsuppressed": after is False}
    out["ok"] = out["checks"]["unsuppressed"]
    return out
