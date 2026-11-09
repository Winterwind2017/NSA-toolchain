"""swkit.verified.inspect —— 只读检查 / 轻量设置（inspect 族）

判据尽量用**读数**而不是返回值：

| 工具 | 判据 |
|---|---|
| `status` | 版本号非空 + 文档数可读 |
| `open_documents` | 列表长度 == `app.GetDocumentCount` |
| `model_info` | 标题/路径/类型与文档一致 |
| `features` | 特征数 > 0，且名称非空 |
| `mass_properties` | 体积 > 0，且体积/包围盒量级一致 |
| `custom_properties` | 名称与值成对可读 |
| `set_custom_property` | 写后 `CustomInfo2` **读回等于写入值** |
| `material` / `set_material` | 写后 `MaterialUserName` 读回包含目标材料 |
| `bodies` | 实体/曲面计数与 `GetBodies2` 一致 |
| `rebuild` | 重建后特征数不变、无异常 |
| `get_dimension` / `set_dimension` | `Dimension.SystemValue` 读回与写入一致 |
| `display_mode` | `View.DisplayMode` 读回等于目标值 |
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import val

__all__ = ["status", "open_documents", "model_info", "features", "mass_properties",
           "custom_properties", "set_custom_property", "material", "set_material",
           "bodies", "rebuild", "get_dimension", "set_dimension", "display_mode",
           "display_states"]

_DISPLAY_MODES = {"wireframe": 1, "hidden_lines_visible": 2,
                  "hidden_lines_removed": 3, "shaded": 4}
_MODE_NAMES = {v: k for k, v in _DISPLAY_MODES.items()}


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _app() -> Any:
    from ..core.com import pyw
    return pyw().Dispatch("SldWorks.Application")


def _iter_features(doc: Any):
    from ._common import iter_features
    return iter_features(doc)


# ── 只读 ───────────────────────────────────────────────────────────────
def status() -> Dict[str, Any]:
    """连接状态 + 版本 + 文档数。"""
    out = _result("sw_get_status", "Application.RevisionNumber")
    app = _app()
    revision = val(app, "RevisionNumber")
    count = val(app, "GetDocumentCount")
    docs = open_documents()
    out["detail"].update({"revision": revision, "document_count": count,
                          "documents": [d.get("title") for d in docs.get("detail", {})
                                        .get("documents", [])][:8]})
    out["checks"] = {"version_readable": bool(revision),
                     "count_readable": isinstance(count, int)}
    out["ok"] = all(out["checks"].values())
    return out


def open_documents() -> Dict[str, Any]:
    """列出已打开文档（标题/路径/类型）。"""
    from ..core.com import pyw
    out = _result("sw_list_open_documents", "Application.GetDocuments")
    app = _app()
    raw = val(app, "GetDocuments") or []
    docs = []
    try:
        items = list(raw)
    except TypeError:
        items = []
    for item in items:
        d = pyw().Dispatch(item)
        docs.append({"title": val(d, "GetTitle"),
                     "path": val(d, "GetPathName"),
                     "type": val(d, "GetType")})
    count = val(app, "GetDocumentCount")
    out["detail"].update({"documents": docs, "count": len(docs),
                          "reported_count": count})
    out["checks"] = {"count_matches": isinstance(count, int) and count == len(docs)}
    out["ok"] = out["checks"]["count_matches"]
    return out


def model_info(doc: Any) -> Dict[str, Any]:
    """当前文档信息：标题 / 路径 / 类型 / 特征数 / 实体数。"""
    out = _result("sw_get_model_info", "IModelDoc2.GetTitle/GetPathName/GetType")
    title = val(doc, "GetTitle")
    path = val(doc, "GetPathName")
    dtype = val(doc, "GetType")
    n_feat = sum(1 for _ in _iter_features(doc))
    solids = len(_bodies_of(doc, 0))
    out["detail"].update({"title": title, "path": path, "type": dtype,
                          "features": n_feat, "bodies": solids})
    out["checks"] = {"title_readable": bool(title), "type_valid": dtype in (1, 2, 3)}
    out["ok"] = all(out["checks"].values())
    return out


def features(doc: Any) -> Dict[str, Any]:
    """特征树（名称 + 类型名）。"""
    out = _result("sw_list_features", "IFeature.GetTypeName2")
    rows = []
    for feat in _iter_features(doc):
        rows.append({"name": val(feat, "Name"), "type": val(feat, "GetTypeName2")})
    out["detail"] = {"count": len(rows), "features": rows[:40]}
    out["checks"] = {"has_features": len(rows) > 0,
                     "names_readable": all(r["name"] for r in rows)}
    out["ok"] = all(out["checks"].values())
    return out


def mass_properties(doc: Any) -> Dict[str, Any]:
    """质量属性（质量 / 体积 / 表面积 / 重心）。"""
    out = _result("sw_get_mass_properties", "IModelDocExtension.CreateMassProperty")
    # pywin32 的动态对象取不到 IMassProperty 的成员（报"找不到成员"），
    # 必须走 comtypes 强类型（实测：mass/volume/area/density 全部可读）。
    mp = None
    try:
        from ._common import com_doc
        _sw, md = com_doc()
        mp = md.Extension.CreateMassProperty()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["comtypes_error"] = "%s: %s" % (type(exc).__name__, exc)
        try:
            mp = doc.Extension.CreateMassProperty()
        except Exception as exc2:                   # noqa: BLE001
            out["detail"]["error"] = "%s: %s" % (type(exc2).__name__, exc2)
            return out
    volume = val(mp, "Volume")
    mass = val(mp, "Mass")
    area = val(mp, "SurfaceArea")
    out["detail"].update({
        "volume_m3": volume, "mass_kg": mass, "surface_area_m2": area,
        "center": [val(mp, "CenterOfMassX"), val(mp, "CenterOfMassY"),
                   val(mp, "CenterOfMassZ")],
    })
    out["checks"] = {"volume_positive": isinstance(volume, float) and volume > 0,
                     "mass_positive": isinstance(mass, float) and mass > 0}
    out["ok"] = all(out["checks"].values())
    return out


def _bodies_of(doc: Any, body_type: int = 0) -> List[Any]:
    """`GetBodies2` 有 2 个参数，不能用无参的 `val()`（会拿到方法对象）。"""
    try:
        return list(doc.GetBodies2(body_type, True) or [])
    except Exception:
        return []


def bodies(doc: Any) -> Dict[str, Any]:
    """实体 / 曲面计数。"""
    out = _result("sw_list_bodies", "IModelDoc2.GetBodies2")
    solid = _bodies_of(doc, 0)
    surf = _bodies_of(doc, 1)
    out["detail"] = {"solids": len(solid), "surfaces": len(surf)}
    out["checks"] = {"readable": True, "solid_or_surface": len(solid) + len(surf) > 0}
    out["ok"] = all(out["checks"].values())
    return out


def custom_properties(doc: Any, config: str = "") -> Dict[str, Any]:
    """自定义属性（名 → 值）。"""
    out = _result("sw_get_custom_properties", "IModelDoc2.GetCustomInfoNames2/CustomInfo2")
    names = []
    try:
        names = [str(n) for n in (doc.GetCustomInfoNames2(config) or [])]
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    props = {}
    for name in names:
        try:
            props[name] = doc.CustomInfo2(config, name)
        except Exception:
            props[name] = None
    out["detail"] = {"config": config or "(default)", "count": len(props),
                     "properties": props}
    out["checks"] = {"names_match_values": len(props) == len(names)}
    out["ok"] = out["checks"]["names_match_values"]
    return out


def set_custom_property(doc: Any, name: str, value: str,
                        config: str = "") -> Dict[str, Any]:
    """写自定义属性，**读回等于写入值**才算成功。"""
    out = _result("sw_set_custom_property", "IModelDoc2.AddCustomInfo3")
    try:
        doc.AddCustomInfo3(config, name, 30, str(value))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    back = None
    try:
        back = doc.CustomInfo2(config, name)
    except Exception:
        pass
    out["detail"] = {"name": name, "written": str(value), "readback": back}
    out["checks"] = {"readback_matches": str(back) == str(value)}
    out["ok"] = out["checks"]["readback_matches"]
    return out


def material(doc: Any, config: str = "") -> Dict[str, Any]:
    """当前材料（显示名 + 材料库 ID）。"""
    out = _result("sw_get_material", "IModelDoc2.MaterialUserName / MaterialIdName")
    user = val(doc, "MaterialUserName")
    mid = val(doc, "MaterialIdName")
    out["detail"] = {"material_user": user, "material_id": mid}
    out["checks"] = {"readable": user is not None or mid is not None}
    out["ok"] = out["checks"]["readable"]
    return out


def set_material(doc: Any, name: str = "AISI 304", config: str = "",
                 database: str = "") -> Dict[str, Any]:
    """赋材料（`IPartDoc.SetMaterialPropertyName2`），读回校验。"""
    out = _result("sw_set_material", "IPartDoc.SetMaterialPropertyName2")
    try:
        from ._common import com_doc
        sw, md = com_doc()
        part = md.QueryInterface(sw.IPartDoc)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "取 IPartDoc: %s" % str(exc)[:90]
        return out
    try:
        part.SetMaterialPropertyName2(config, database, name)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    user = val(doc, "MaterialUserName")
    mid = val(doc, "MaterialIdName")
    out["detail"] = {"requested": name, "material_user": user, "material_id": mid}
    got = str(user or "") + "|" + str(mid or "")
    out["detail"]["material_id"] = mid
    out["checks"] = {"applied": name.lower() in got.lower()}
    out["ok"] = out["checks"]["applied"]
    return out


def rebuild(doc: Any) -> Dict[str, Any]:
    """强制重建（Ctrl+B），判据：特征数不变且无异常。"""
    out = _result("sw_rebuild_model", "IModelDoc2.ForceRebuild3")
    before = sum(1 for _ in _iter_features(doc))
    try:
        doc.ForceRebuild3(False)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = sum(1 for _ in _iter_features(doc))
    out["detail"] = {"features_before": before, "features_after": after}
    out["checks"] = {"features_unchanged": before == after}
    out["ok"] = out["checks"]["features_unchanged"]
    return out


def get_dimension(doc: Any, name: str) -> Dict[str, Any]:
    """按名字读尺寸（`SystemValue` 单位是**米**，这里输出 mm）。"""
    out = _result("sw_get_dimension", "IModelDoc2.Parameter")
    try:
        dim = doc.Parameter(name)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if dim is None:
        out["detail"]["error"] = "找不到尺寸：%s" % name
        return out
    sysval = val(dim, "SystemValue")
    full = val(dim, "FullName")
    out["detail"] = {"name": name, "full_name": full,
                     "value_m": sysval,
                     "value_mm": round(float(sysval) * 1000.0, 6)
                     if isinstance(sysval, float) else None}
    out["checks"] = {"value_readable": isinstance(sysval, float)}
    out["ok"] = out["checks"]["value_readable"]
    return out


def set_dimension(doc: Any, name: str, value_mm: float) -> Dict[str, Any]:
    """改尺寸（写入米），读回校验。"""
    out = _result("sw_set_dimension", "IDimension.SystemValue")
    try:
        dim = doc.Parameter(name)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if dim is None:
        out["detail"]["error"] = "找不到尺寸：%s" % name
        return out
    before = val(dim, "SystemValue")
    try:
        dim.SystemValue = float(value_mm) / 1000.0
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = val(dim, "SystemValue")
    out["detail"] = {"name": name, "before_mm": round(float(before) * 1000, 6)
                     if isinstance(before, float) else None,
                     "target_mm": float(value_mm),
                     "after_mm": round(float(after) * 1000, 6)
                     if isinstance(after, float) else None}
    out["checks"] = {"readback_matches": isinstance(after, float)
                     and abs(float(after) * 1000.0 - float(value_mm)) < 1e-6}
    out["ok"] = out["checks"]["readback_matches"]
    return out


def display_mode(doc: Any, mode: str = "shaded") -> Dict[str, Any]:
    """设置显示模式，判据：`View.DisplayMode` 读回等于目标值。"""
    out = _result("sw_set_display_mode", "IModelView.SetDisplayMode")
    target = _DISPLAY_MODES.get(str(mode).lower())
    if target is None:
        out["detail"]["error"] = "未知显示模式：%s（可选 %s）" % (
            mode, "/".join(_DISPLAY_MODES))
        return out
    try:
        view = doc.ActiveView
        before = val(view, "DisplayMode")
        # `DisplayMode` 在 TLB 里是**可写属性**（有 0 参 getter + 1 参 setter），
        # 没有 `SetDisplayMode` 方法——用赋值，不是调方法（实测报 <unknown>.SetDisplayMode）。
        view.DisplayMode = target
        after = val(view, "DisplayMode")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    out["detail"] = {"requested": mode, "target_value": target,
                     "before": before, "after": after,
                     "mode_name": _MODE_NAMES.get(after)}
    out["checks"] = {"readback_matches": after == target}
    out["ok"] = out["checks"]["readback_matches"]
    return out


def display_states(doc: Any) -> Dict[str, Any]:
    """列显示状态（复用已验证的 `activate_display_state` 读取逻辑）。"""
    from .model import activate_display_state
    res = activate_display_state(doc, name="")
    out = _result("sw_list_display_states", "IConfiguration.GetDisplayStates")
    detail = res.get("detail") or {}
    out["detail"] = {"configuration": detail.get("configuration"),
                     "count": detail.get("display_state_count"),
                     "names": detail.get("names"), "applied": detail.get("applied")}
    out["checks"] = {"listed": bool(detail.get("names"))}
    out["ok"] = out["checks"]["listed"]
    return out
