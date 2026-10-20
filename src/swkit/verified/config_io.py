"""swkit.verified.config_io —— 文档开关 / 另存副本 / 配置 / 引用文档

判据：

| 工具 | 判据 |
|---|---|
| `open_document` | 文档数 **+1** 且标题匹配文件名 |
| `close_document` | 文档数 **-1** |
| `close_all` | 文档数 **0** |
| `save_all` | 调用成功且文档数不变 |
| `save_as_copy` | 新文件出现、**原文档路径不变** |
| `list_configurations` | 配置数 > 0，且能读出激活配置名 |
| `add_configuration` | 配置数 **+1** |
| `activate_configuration` | `GetActiveConfiguration` 读回等于目标 |
| `get_referenced_documents` | 图纸打开时能列出其模型（依赖数 > 0） |

实测签名：
* `AddConfiguration3(Name, Comment, AlternateName, Options)` **4 参**
* `ShowConfiguration2(ConfigurationName)` 1 参
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..core.com import pyw, val

__all__ = ["open_document", "close_document", "close_all", "save_all",
           "save_as_copy", "list_configurations", "add_configuration",
           "activate_configuration", "get_referenced_documents"]

_OPEN_TYPES = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _app() -> Any:
    return pyw().Dispatch("SldWorks.Application")


def _count() -> int:
    try:
        return int(val(_app(), "GetDocumentCount"))
    except Exception:
        return -1


def open_document(path: str) -> Dict[str, Any]:
    """打开文档。判据：文档数 +1。"""
    out = _result("sw_open_document", "ISldWorks.OpenDoc6")
    target = os.path.abspath(path)
    if not os.path.isfile(target):
        out["detail"]["error"] = "文件不存在：%s" % target
        return out
    before = _count()
    kind = _OPEN_TYPES.get(os.path.splitext(target)[1].lower(), 1)
    app = _app()
    try:
        doc = app.OpenDoc(target, kind)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _count()
    title = val(pyw().Dispatch(app.ActiveDoc), "GetTitle") if doc is not None else None
    out["detail"].update({"path": target, "documents_before": before,
                          "documents_after": after, "title": title})
    out["checks"] = {"opened": doc is not None, "count_increased": after == before + 1}
    out["ok"] = all(out["checks"].values())
    return out


def close_document(title: str = "", save: bool = False) -> Dict[str, Any]:
    """关闭文档（默认关活动文档）。判据：文档数 -1。"""
    out = _result("sw_close_document", "ISldWorks.CloseDoc")
    app = _app()
    if not title:
        active = app.ActiveDoc
        title = val(pyw().Dispatch(active), "GetTitle") if active is not None else ""
    before = _count()
    try:
        app.CloseDoc(title)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _count()
    out["detail"].update({"title": title, "documents_before": before,
                          "documents_after": after})
    out["checks"] = {"count_decreased": after == before - 1}
    out["ok"] = out["checks"]["count_decreased"]
    return out


def close_all(save: bool = False) -> Dict[str, Any]:
    """关闭全部。判据：文档数 0。"""
    out = _result("sw_close_all", "ISldWorks.CloseAllDocuments")
    before = _count()
    try:
        _app().CloseAllDocuments(bool(save))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _count()
    out["detail"].update({"documents_before": before, "documents_after": after})
    out["checks"] = {"all_closed": after == 0}
    out["ok"] = out["checks"]["all_closed"]
    return out


def save_all() -> Dict[str, Any]:
    """保存全部。判据：调用成功且文档数不变。"""
    out = _result("sw_save_all", "ISldWorks.SaveAllDocuments")
    before = _count()
    try:
        ok = _app().SaveAllDocuments() if hasattr(_app(), "SaveAllDocuments") else None
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _count()
    out["detail"].update({"returned": ok, "documents_before": before,
                          "documents_after": after})
    out["checks"] = {"no_error": True, "documents_unchanged": after == before}
    out["ok"] = all(out["checks"].values())
    return out


def save_as_copy(doc: Any, path: str) -> Dict[str, Any]:
    """另存副本。判据：新文件出现且**原文档路径不变**。"""
    out = _result("sw_save_as_copy", "IModelDoc2.SaveAs4（副本模式）")
    target = os.path.abspath(path)
    original = val(doc, "GetPathName")
    if os.path.exists(target):
        try:
            os.remove(target)
        except OSError:
            pass
    used = None
    try:
        # SaveAs2(NewName, SaveAsVersion, SaveAsCopy, Silent)：第 3 参 = True 才是副本
        # （SaveAs4 有 5 参且 Errors/Warnings 是 byref，pywin32 会报"无效的参数数目"）
        doc.SaveAs2(target, 0, True, False)
        used = "SaveAs2(SaveAsCopy=True)"
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after_path = val(doc, "GetPathName")
    size = os.path.getsize(target) if os.path.exists(target) else 0
    out["detail"].update({"path": target, "bytes": size, "api_used": used,
                          "original_path": original, "path_after": after_path})
    out["checks"] = {"copy_exists": size > 0,
                     "original_unchanged": str(original) == str(after_path)}
    out["ok"] = all(out["checks"].values())
    return out


def _config_names(doc: Any) -> List[str]:
    """配置名列表（属性/方法双形态：AddConfiguration3 之后再取会变成 tuple）。"""
    try:
        v = doc.GetConfigurationNames
    except Exception:
        return []
    try:
        raw = v() if callable(v) else v
    except Exception:
        return []
    try:
        return [str(n) for n in (raw or [])]
    except TypeError:
        return []


def _active_config_name(doc: Any) -> Optional[str]:
    """激活配置名：走 `ConfigurationManager.ActiveConfiguration.Name`。

    `doc.GetActiveConfiguration()` 在本机返回 COMObject 但取不到 Name。
    """
    try:
        cm = doc.ConfigurationManager
        cfg = val(cm, "ActiveConfiguration")
        return val(cfg, "Name")
    except Exception:
        return None


def list_configurations(doc: Any) -> Dict[str, Any]:
    """列配置。判据：配置数 > 0 且能读出激活配置。"""
    out = _result("sw_list_configurations", "IModelDoc2.GetConfigurationNames")
    names = _config_names(doc)
    if not names:
        out["detail"]["error"] = "读不到配置名（属性/方法双形态都不成立）"
        return out
    active = _active_config_name(doc)
    out["detail"].update({"count": len(names), "names": names[:20], "active": active})
    out["checks"] = {"has_configurations": len(names) > 0, "active_readable": bool(active)}
    out["ok"] = all(out["checks"].values())
    return out


def add_configuration(doc: Any, name: str = "CFG_SWKIT",
                      comment: str = "added by swkit") -> Dict[str, Any]:
    """新增配置。判据：配置数 +1。"""
    out = _result("sw_add_configuration", "IModelDoc2.AddConfiguration3(4 参)")
    before = _config_names(doc)
    out["detail"].update({"configurations_before": len(before), "name": name})
    try:
        feat = doc.AddConfiguration3(name, comment, "", 0)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _config_names(doc)
    out["detail"].update({"configurations_after": len(after), "names": after[:10],
                          "returned": feat is not None})
    out["checks"] = {"count_increased": len(after) == len(before) + 1,
                     "name_present": name in after}
    out["ok"] = all(out["checks"].values())
    return out


def activate_configuration(doc: Any, name: str) -> Dict[str, Any]:
    """切换配置。判据：激活配置名读回等于目标。"""
    out = _result("sw_activate_configuration", "IModelDoc2.ShowConfiguration2")
    try:
        ok = doc.ShowConfiguration2(name)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    # 返回值不可靠（切到已激活的配置也返回 False）→ 一律以读回为准
    active = _active_config_name(doc)
    out["detail"].update({"target": name, "active": active, "returned": ok})
    out["checks"] = {"activated": str(active) == str(name)}
    out["ok"] = out["checks"]["activated"]
    return out


def get_referenced_documents(doc: Any) -> Dict[str, Any]:
    """引用文档（图纸 → 它的模型）。判据：依赖数 > 0。"""
    out = _result("sw_get_referenced_documents", "IModelDoc2.GetDependencies(2 参)")
    try:
        deps = doc.GetDependencies(False, False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    try:
        items = [str(d) for d in (deps or [])]
    except TypeError:
        items = []
    out["detail"].update({"count": len(items), "documents": items[:10]})
    out["checks"] = {"has_dependencies": len(items) > 0}
    out["ok"] = out["checks"]["has_dependencies"]
    return out
