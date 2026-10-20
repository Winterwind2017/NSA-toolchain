r"""swkit.verified.model —— 文档级元操作（显示状态、材料库）

| 工具 | 真实 API | 判据 |
|---|---|---|
| `activate_display_state` | `IConfiguration.GetDisplayStates` / `ApplyDisplayState(name)` | 名称列表非空且 `ApplyDisplayState` 返回 True |
| `list_materials` | **直接解析 `.sldmat`（XML）** | 类别/材料计数（本机 3 库 / 29 类 / 474 材料） |

为什么材料要走 XML：30 个类型库里 202 个含 `material` 的方法**没有一个能枚举材料库**
（只有 `MaterialIdName` / `MaterialPropertyValues` 这类单实体读写）。材料库本体是
`lang\<locale>\sldmaterials\*.sldmat`，带命名空间 `{http://www.solidworks.com/sldmaterials}`。
"""

from __future__ import annotations

import glob
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ..core.com import val

__all__ = ["activate_display_state", "list_materials", "materials_dirs"]

_SW_INSTALL = os.environ.get("SWKIT_SW_INSTALL") or \
    r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
_LOCALES = ("chinese-simplified", "english", "chinese-traditional")


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def activate_display_state(doc_w: Any, name: str = "") -> Dict[str, Any]:
    """激活显示状态。`name` 为空则依次尝试所有可用状态。"""
    out = _result("sw_activate_display_state", "IConfiguration.ApplyDisplayState")
    try:
        cfg = doc_w.ConfigurationManager.ActiveConfiguration
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    names = []
    try:
        states = val(cfg, "GetDisplayStates") or []
        names = [str(x) for x in states]
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["read_error"] = str(exc)[:100]
    count = val(cfg, "GetDisplayStatesCount", -1)
    out["detail"].update({"configuration": val(cfg, "Name"),
                          "display_state_count": count, "names": names})
    if not names:
        out["detail"]["note"] = "该文档没有显示状态（不是缺陷，需要先在 SolidWorks 里建一个）"
        out["checks"] = {"has_display_states": False}
        return out
    order = ([name] if name else []) + [n for n in names if n != name]
    applied = None
    for nm in order:
        ok = False
        try:
            ok = bool(cfg.ApplyDisplayState(nm))
        except Exception as exc:                    # noqa: BLE001
            out["detail"].setdefault("attempts", []).append(
                {"name": nm, "error": str(exc)[:80]})
            continue
        out["detail"].setdefault("attempts", []).append({"name": nm, "returned": ok})
        if ok:
            applied = nm
            break
    out["detail"]["applied"] = applied
    out["checks"] = {"has_display_states": True, "apply_returned_true": applied is not None}
    out["ok"] = all(out["checks"].values())
    return out


def materials_dirs(extra: Optional[str] = None) -> List[str]:
    """候选材料库目录：显式目录 → 各语言包 → 用户自定义库。"""
    dirs: List[str] = []
    env = os.environ.get("SWKIT_MATERIALS_DIR")
    for cand in (extra, env):
        if cand:
            dirs.append(cand)
    base = os.path.join(_SW_INSTALL, "lang")
    for loc in _LOCALES:
        dirs.append(os.path.join(base, loc, "sldmaterials"))
    dirs.append(os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                             "SolidWorks", "SOLIDWORKS 2025"))
    return dirs


def _local(elem: Any, tag: str) -> List[Any]:
    return [e for e in elem.iter() if e.tag.rsplit("}", 1)[-1] == tag]


def list_materials(directory: str = "", name_filter: str = "",
                   limit: int = 20, verbose: bool = False) -> Dict[str, Any]:
    """列举材料库。不打开 SolidWorks，直接解析 `.sldmat`。"""
    out = _result("sw_list_materials", "解析 .sldmat（XML）")
    # 只看"第一个确实有库"的目录：跨语言包全扫会把同一材料重复计（实测 6 库/948 材料
    # 其实是 3 库/474 的两份语言包副本）。需要全扫时显式传 directory。
    files: List[str] = []
    used_dirs: List[str] = []
    for d in materials_dirs(directory or None):
        if not os.path.isdir(d):
            continue
        found = sorted(glob.glob(os.path.join(d, "*.sldmat")))
        if found:
            used_dirs.append(d)
            files.extend(found)
            break
    files = sorted(set(files))
    out["detail"]["dirs"] = used_dirs
    out["detail"]["files"] = [os.path.basename(f) for f in files]
    if not files:
        out["detail"]["error"] = "没有找到 .sldmat（可用 SWKIT_MATERIALS_DIR 指定）"
        return out
    total_cats, total_mats, matched, per_file = 0, 0, 0, []
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except Exception as exc:                    # noqa: BLE001
            per_file.append({"file": os.path.basename(path),
                             "error": str(exc)[:80]})
            continue
        cats = _local(root, "classification")
        mats = _local(root, "material")
        total_cats += len(cats)
        total_mats += len(mats)
        row = {"file": os.path.basename(path),
               "categories": len(cats), "materials": len(mats)}
        if verbose:
            row["samples"] = [
                {"category": c.get("name"),
                 "materials": [m.get("name") for m in _local(c, "material")][:6]}
                for c in cats[:limit]
            ]
        per_file.append(row)
        if name_filter:
            for m in mats:
                nm = m.get("name") or ""
                if name_filter.lower() in nm.lower():
                    matched += 1
                    if matched <= limit:
                        out["detail"].setdefault("matches", []).append(
                            {"name": nm, "file": os.path.basename(path)})
    out["detail"].update({"per_file": per_file, "categories": total_cats,
                          "materials": total_mats, "files_total": len(files)})
    if name_filter:
        out["detail"]["match_count"] = matched
    out["checks"] = {"materials_found": total_mats > 0}
    out["ok"] = all(out["checks"].values())
    return out
