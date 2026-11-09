"""swkit.verified.dimxpert —— DimXpert 读取（独立类型库 swdimxpert.tlb）

判据（可区分，不是"能调通"）：

| 场景 | `DimXpertPart` | 要素/标注计数 |
|---|---|---|
| `create=False` 且该配置还没建过 schema | **None** | 读不到 |
| `create=True`（新建 schema） | 对象 | **0 / 0**，schema 名 `模式2` |

## 这条 API 为什么以前"找不到成员"

`sw_dxp` 在旧实现里一直失败，根因是**用错了类型库**：DimXpert 的接口
（`IDimXpertManager` / `IDimXpertPart` / `IDimXpertAnnotation`）在
`<安装目录>\\swdimxpert.tlb`（69 KB，123 个接口）里，**不在** `sldworks.tlb`。
入口仍走主 API：`IModelDocExtension.DimXpertManager(Configuration, CreateSchema)`。

## 已知未打通

`IDimXpertPart.AutoDimensionScheme(option)` 实测返回 **False**、标注数仍 0
（每次调用后 `GetAnnotationCount` 不变）——需要预设 option 的
`PartType`/`ToleranceType` 或先选要素。因此**自动标注**未转正，只转正读取。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import val

__all__ = ["info", "auto_dimension_scheme"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _dv(obj: Any, name: str) -> Any:
    """成员可能是属性也可能是方法，两种都试。

    坑：pywin32 的 COM 对象（CDispatch）**本身可调用**，若用 `callable()` 判断
    会把属性（如 `DimXpertPart`）误当方法调用，结果拿到 None。这里只对真正的
    Python 绑定方法（`types.MethodType`）才调用。
    """
    import types

    try:
        node = getattr(obj, name)
    except Exception:
        return None
    if isinstance(node, types.MethodType):
        try:
            return node()
        except Exception:
            return None
    return node


def info(doc: Any, config: str = "", create: bool = False) -> Dict[str, Any]:
    """读 DimXpert 状态：schema 名、要素数、标注数。"""
    out = _result("sw_dxp", "IModelDocExtension.DimXpertManager + IDimXpertPart")
    try:
        mgr = doc.Extension.DimXpertManager(str(config), bool(create))
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if mgr is None:
        out["detail"]["error"] = "取不到 DimXpertManager"
        return out
    out["detail"].update({"configuration": config or "(活动配置)",
                          "create_schema": bool(create),
                          "schema_name": _dv(mgr, "SchemaName")})
    part = _dv(mgr, "DimXpertPart")
    out["detail"]["part_available"] = part is not None
    if part is None:
        # create=False 且尚未建 schema：这是**正常**结果，但要如实标出来
        out["checks"] = {"manager_ok": True, "schema_absent": True}
        out["ok"] = True
        return out
    feat = _dv(part, "GetFeatureCount")
    ann = _dv(part, "GetAnnotationCount")
    out["detail"].update({"feature_count": feat, "annotation_count": ann})
    out["checks"] = {
        "manager_ok": True,
        "feature_count_readable": isinstance(feat, int) and feat >= 0,
        "annotation_count_readable": isinstance(ann, int) and ann >= 0,
    }
    out["ok"] = all(out["checks"].values())
    return out


def auto_dimension_scheme(doc: Any, config: str = "") -> Dict[str, Any]:
    """自动尺寸方案（**未打通**：实测返回 False、标注数不变）。保留以便复现。"""
    out = _result("sw_dimxpert_autodim", "IDimXpertPart.AutoDimensionScheme")
    res = info(doc, config, create=True)
    part = None
    try:
        mgr = doc.Extension.DimXpertManager(str(config), True)
        part = _dv(mgr, "DimXpertPart")
    except Exception:
        part = None
    if part is None:
        out["detail"]["error"] = "没有 DimXpertPart"
        return out
    before = _dv(part, "GetAnnotationCount")
    opt = _dv(part, "GetAutoDimSchemeOption")
    try:
        ret = part.AutoDimensionScheme(opt)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = _dv(part, "GetAnnotationCount")
    out["detail"].update({"returned": ret, "annotations_before": before,
                          "annotations_after": after})
    out["checks"] = {"annotations_increased":
                     isinstance(before, int) and isinstance(after, int)
                     and after > before}
    out["ok"] = out["checks"]["annotations_increased"]
    return out
