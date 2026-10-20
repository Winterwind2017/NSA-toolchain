"""swkit.mcp.server —— MCP 入口（stdio）

两条明确分层的工具集，**不混着卖**：

* **Tier A / verified** —— 本机实测通过、带判据的能力（`sw_status`、`sw_registry`、
  `sw_document_info`、`sw_pattern_component`、`sw_mirror_component`）。
* **Tier B / api** —— 对高层 API（`SolidWorksApp` 的 ~70 个方法）的透传。
  响应里永远带 `"status": "unverified"`，提醒调用方：这类操作**尚未逐个复核**。

这样 agent 能拿到广度，但不会把"没验证过"当成"已验证"。

运行：

    swkit-mcp                 # 或  python -m swkit.mcp.server
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .. import __version__
from ..core.com import dispatch, pyw, val
from ..registry import REGISTRY, summary
from ..verified.assembly import (
    component_names, components, mirror_components, pattern_component,
)

try:                                    # pragma: no cover - 依赖可选
    from mcp.server.fastmcp import FastMCP
except Exception as exc:                # pragma: no cover
    raise SystemExit("需要 mcp 包：pip install 'mcp>=1.0'\n%s" % exc)

mcp = FastMCP("swkit")

# SolidWorks 的 COM 不是线程安全的：所有调用串行化，且每个调用自己 CoInitialize。
_LOCK = threading.RLock()


def _com(fn, *args, **kwargs):
    """在锁内 + 已初始化 COM 的线程上执行一次调用。"""
    import pythoncom
    with _LOCK:
        pythoncom.CoInitialize()
        try:
            return fn(*args, **kwargs)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _app():
    return dispatch("SldWorks.Application")


def _doc(app):
    doc = app.ActiveDoc
    return pyw().Dispatch(doc) if doc is not None else None


@mcp.tool(name="sw_status")
def sw_status() -> Dict[str, Any]:
    """连接状态、打开文档数、注册表摘要。任何操作前先调这个。"""
    def _do():
        app = _app()
        return {
            "connected": True,
            "revision": str(val(app, "RevisionNumber", "")),
            "open_documents": int(val(app, "GetDocumentCount", 0) or 0),
            "active_document": str(val(app, "GetTitle", "") or ""),
            "registry": summary(),
            "swkit_version": __version__,
        }
    try:
        return _com(_do)
    except Exception as exc:
        return {"connected": False, "error": "%s: %s" % (type(exc).__name__, exc),
                "swkit_version": __version__}


@mcp.tool(name="sw_registry")
def sw_registry(status: str = "") -> Dict[str, Any]:
    """查"哪些工具真的能用"及其依据。status 留空返回全部，可填 verified/unstable/broken。"""
    rows: List[Dict[str, str]] = []
    for entry in REGISTRY.values():
        if status and entry.status != status:
            continue
        rows.append({"name": entry.name, "group": entry.group, "status": entry.status,
                     "implemented": entry.implemented, "api": entry.api,
                     "evidence": entry.evidence, "note": entry.note})
    rows.sort(key=lambda r: (not r["implemented"], r["status"] != "verified",
                             r["group"], r["name"]))
    return {"count": len(rows), "summary": summary(), "tools": rows}


@mcp.tool(name="sw_document_info")
def sw_document_info() -> Dict[str, Any]:
    """当前文档概览：标题、类型、特征数、实体数、组件数。

    判据用计数而不是返回值——SolidWorks 很多"成功"的调用返回 None/0。
    """
    def _do():
        app = _app()
        doc = _doc(app)
        if doc is None:
            return {"ok": False, "error": "没有打开的文档"}
        feats, feat = 0, None
        try:
            feat = doc.FirstFeature()
        except Exception:
            feat = None
        while feat is not None and feats < 500:
            feats += 1
            try:
                feat = pyw().Dispatch(feat).GetNextFeature()
            except Exception:
                break
        info: Dict[str, Any] = {
            "ok": True,
            "title": str(val(doc, "GetTitle", "")),
            "type": int(val(doc, "GetType", 0) or 0),   # 1=零件 2=装配 3=工程图
            "features": feats,
        }
        bodies = None
        for getter in ("GetBodies2",):
            try:
                bodies = list(getattr(doc, getter)(0, True) or [])
                break
            except Exception:
                bodies = None
        if bodies is not None:
            info["bodies"] = len(bodies)
        comps = components(doc)
        if comps:
            info["components"] = len(comps)
            info["component_names"] = component_names(doc)
        return info
    return _com(_do)


@mcp.tool(name="sw_pattern_component")
def sw_pattern_component(kind: str = "linear", count: int = 3,
                         spacing: float = 0.05,
                         angle_deg: float = 120.0,
                         component_index: int = 0) -> Dict[str, Any]:
    """组件阵列（verified）。kind=linear|circular；spacing 单位米；angle_deg 角度。

    内部用**官方正确标记**：组件 mark=1、方向 mark=2。返回值里的 checks 就是判据。
    """
    import math

    def _do():
        doc = _doc(_app())
        if doc is None:
            return {"ok": False, "error": "没有打开的文档"}
        return pattern_component(doc, kind=kind, count=count, spacing=spacing,
                                 angle=math.radians(angle_deg),
                                 component_index=component_index)
    return _com(_do)


@mcp.tool(name="sw_mirror_component")
def sw_mirror_component(plane: str = "前视基准面", component_filter: str = "",
                        mirror_type: int = 2) -> Dict[str, Any]:
    """镜像组件（verified）。mirror_type：0=包围盒中心 1=质心 2=组件原点。"""
    def _do():
        doc = _doc(_app())
        if doc is None:
            return {"ok": False, "error": "没有打开的文档"}
        return mirror_components(doc, plane_name=plane,
                                 component_filter=component_filter,
                                 mirror_type=mirror_type)
    return _com(_do)


@mcp.tool(name="sw_api")
def sw_api(op: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """透传高层 API（**unverified**）：op 是 `SolidWorksApp` 的方法名。

    例：{"op": "new_part"}、{"op": "extrude", "params": {"depth": 0.02}}。
    先用 `sw_api("list_operations")` 看有哪些方法。
    """
    from ..api.app import SolidWorksApp

    def _do():
        app = SolidWorksApp()
        app.connect()
        if op == "list_operations":
            if hasattr(app, "disconnect"):
                pass
            return {"ok": True, "status": "unverified",
                    "operations": [n for n in dir(app)
                                   if not n.startswith("_") and callable(getattr(app, n))]}
        fn = getattr(app, op, None)
        if fn is None or op.startswith("_"):
            return {"ok": False, "status": "unverified", "error": "没有这个方法：%s" % op}
        try:
            result = fn(**(params or {}))
        except Exception as exc:
            return {"ok": False, "status": "unverified",
                    "error": "%s: %s" % (type(exc).__name__, exc)}
        return {"ok": True, "status": "unverified", "result": result}
    return _com(_do)


@mcp.tool(name="sw_sim_status")
def sw_sim_status(open_path: str = "") -> Dict[str, Any]:
    """Simulation 诊断（verified）：当前文档、材质、加载项、研究列表。"""
    from ..study import sim
    return _com(lambda: sim.status(open_path))


@mcp.tool(name="sw_sim_solve")
def sw_sim_solve(open_path: str = "", restraint_face: int = 0,
                 force_face: int = 1, force_n: float = 100.0,
                 material: str = "") -> Dict[str, Any]:
    """一条龙静力分析（verified，**约 13–15 分钟**，star.exe 峰值 ~15 GB）。

    位移可靠；应力注意：固定端锐边是应力奇异（伪值），且重开文档后常读不到（code 1）。
    """
    from ..study import sim
    return _com(lambda: sim.solve(open_path, restraint_face=restraint_face,
                                  force_face=force_face, force_n=force_n,
                                  material=material))


@mcp.tool(name="sw_sim_read")
def sw_sim_read(open_path: str = "", study: str = "") -> Dict[str, Any]:
    """读已有静力结果（verified）。应力不可用时会返回 stress_available=False。"""
    from ..study import sim
    return _com(lambda: sim.read(open_path, study))


@mcp.tool(name="sw_motion_read")
def sw_motion_read(open_path: str = "", study: str = "",
                   component: str = "", samples: int = 11) -> Dict[str, Any]:
    """读 Motion 结果（verified）：位移/速度/加速度采样。

    底层用 `GetResults(4)`——索引 1/2 是空壳（IsOutOfDate=True、值恒 0）。
    """
    from ..study import motion
    return _com(lambda: motion.read(open_path, study=study, component=component,
                                    samples=samples))


@mcp.tool(name="sw_docs_stats")
def sw_docs_stats() -> Dict[str, Any]:
    """DocumentMgr 索引统计（verified）：文件数、属性条目、组件行、视图行、表格数。"""
    from ..meta import docs
    return _com(lambda: docs.stats())


@mcp.tool(name="sw_docs_query")
def sw_docs_query(prop: str = "", folder: str = "", ext: str = "",
                  limit: int = 0) -> Dict[str, Any]:
    """按属性/目录/扩展名查索引（verified）。`prop` 支持 `名=值`。

    注意：**没有全文检索**（底层只有 --prop/--dir/--ext）。
    """
    from ..meta import docs
    return _com(lambda: docs.query(prop=prop, folder=folder, ext=ext, limit=limit))


@mcp.tool(name="sw_props")
def sw_props(file: str = "") -> Dict[str, Any]:
    """单文件自定义属性（verified）；不给 file 则做 Simulation 加载项自检。"""
    from ..meta import props as props_mod
    return _com(lambda: props_mod.props(file) if file else props_mod.sim_status())


@mcp.tool(name="sw_vba_dump")
def sw_vba_dump(swp: str) -> Dict[str, Any]:
    """导出 `.swp` 内嵌 VBA 源码（verified）。只读。"""
    from ..meta import vba
    return _com(lambda: vba.dump(swp))


def main() -> None:
    mcp.run()


if __name__ == "__main__":              # pragma: no cover
    main()
