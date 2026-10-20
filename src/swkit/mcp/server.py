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

# 注意：FastMCP 的 constructor 没有 version 参数，serverInfo.version 会显示底层 mcp 库版本；
# 本包版本请从 `sw_status` 的 swkit_version 或 `swkit --version` 看。
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


@mcp.tool(name="sw_new_drawing")
def sw_new_drawing(model: str, template: str = "", view: str = "front",
                   x: float = 0.15, y: float = 0.15) -> Dict[str, Any]:
    """从零件建图并插主视图（出图夹具）。中文模板只认本地化视图名（`*前视`）。"""
    from ..verified import drawing
    return _com(lambda: drawing.new_drawing(model, template=template, view=view,
                                            x=x, y=y))


@mcp.tool(name="sw_add_center_mark")
def sw_add_center_mark(x: float = 0.05) -> Dict[str, Any]:
    """中心标记（verified）：判据 `IView.GetCenterMarks` 计数 +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.center_mark(doc, x=x))
    return _com(_do)


@mcp.tool(name="sw_add_centerline")
def sw_add_centerline() -> Dict[str, Any]:
    """中心线（verified）：判据 `IView.GetCenterLines` 计数 +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.centerline(doc))
    return _com(_do)


@mcp.tool(name="sw_add_datum_feature")
def sw_add_datum_feature() -> Dict[str, Any]:
    """基准符号（verified）：判据 `IView.GetDatumTagCount` +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.symbol(doc, "datum"))
    return _com(_do)


@mcp.tool(name="sw_add_gtol")
def sw_add_gtol() -> Dict[str, Any]:
    """形位公差（verified）：判据 `IView.GetGTolCount` +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.symbol(doc, "gtol"))
    return _com(_do)


@mcp.tool(name="sw_add_weld_symbol")
def sw_add_weld_symbol() -> Dict[str, Any]:
    """焊接符号（verified）：判据 `IView.GetWeldSymbolCount` +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.symbol(doc, "weld"))
    return _com(_do)


@mcp.tool(name="sw_add_surface_finish")
def sw_add_surface_finish(x: float = 0.05, y: float = 0.05) -> Dict[str, Any]:
    """表面粗糙度（**unverified**）：调用会执行，但本机没有可读计数，无法证明符号生成。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.surface_finish(doc, x=x, y=y))
    return _com(_do)


@mcp.tool(name="sw_note")
def sw_note(text: str, x: float = 0.05, y: float = 0.05) -> Dict[str, Any]:
    """注释（verified）：判据 文本读回 + 位置读回。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.note(doc, text=text, x=x, y=y))
    return _com(_do)


@mcp.tool(name="sw_add_annotation")
def sw_add_annotation(text: str, x: float = 0.05, y: float = 0.05) -> Dict[str, Any]:
    """图纸注释（verified，与 sw_note 同一实现）。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.note(doc, text=text, x=x, y=y))
    return _com(_do)


@mcp.tool(name="sw_add_auxiliary_view")
def sw_add_auxiliary_view() -> Dict[str, Any]:
    """辅助视图（verified）：`CreateAuxiliaryView()` 零参、靠选择集；判据视图数 +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.aux_view(doc))
    return _com(_do)


@mcp.tool(name="sw_create_section_view")
def sw_create_section_view(plane: str = "前视基准面", offset: float = 0.0) -> Dict[str, Any]:
    """剖视图（verified）：`CreateSectionViewData` + `CreateSectionView`，成功后自动复位。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.section_view(doc, plane, offset))
    return _com(_do)


@mcp.tool(name="sw_add_broken_view")
def sw_add_broken_view(orientation: int = 0, position: float = 0.05,
                       size: float = 0.01) -> Dict[str, Any]:
    """断裂视图（verified）：判据是 `GetBreakLines` 数量（**不新增视图**）。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        if doc is None:
            return {"ok": False, "error": "没有打开的文档"}
        return drawing.broken_view(drawing.first_model_view(doc), orientation,
                                   position, size)
    return _com(_do)


@mcp.tool(name="sw_add_drawing_dimension")
def sw_add_drawing_dimension(x: float = 0.12, y: float = 0.12) -> Dict[str, Any]:
    """图纸尺寸（verified）：选两条边 → `AddDimension2`；判据 `GetDisplayDimensions` +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.drawing_dimension(doc, x, y))
    return _com(_do)


@mcp.tool(name="sw_add_hole_table")
def sw_add_hole_table(x: float = 0.10, y: float = 0.16) -> Dict[str, Any]:
    """孔表（verified）：先 `ActivateView` 再 `InsertHoleTable2`；判据表格数 +1。"""
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.hole_table(doc, x, y))
    return _com(_do)


@mcp.tool(name="sw_add_balloon")
def sw_add_balloon(x: float = 0.10, y: float = 0.16) -> Dict[str, Any]:
    """自动球标（verified）：先 `InsertBomTable2`（7 参、`BomType` 必须 1/2/3），
    再**选中视图**（`SelectByID2(name,"DRAWINGVIEW")`）→ `AutoBalloon2(1, True)`。

    实测：装配图 2 组件 → 2 个气球、2 条注释。零件图没有 BOM 项，会如实返回 `bom_available=False`。
    """
    from ..verified import drawing
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else drawing.balloon(doc, x, y))
    return _com(_do)


@mcp.tool(name="sw_check_interference")
def sw_check_interference() -> Dict[str, Any]:
    """干涉检查（verified）。**count=0 也算成功**——判据是"能读到计数"。

    A/B 实测：两件重叠 → 1 处；分开 → 0 处。
    """
    from ..verified import asm_ops
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else asm_ops.check_interference(doc))
    return _com(_do)


@mcp.tool(name="sw_fix_component")
def sw_fix_component(component_index: int = 0) -> Dict[str, Any]:
    """固定组件（verified）：判据 `IsFixed=True`。"""
    from ..verified import asm_ops
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else asm_ops.fix_component(doc, component_index=component_index))
    return _com(_do)


@mcp.tool(name="sw_show_all_components")
def sw_show_all_components() -> Dict[str, Any]:
    """显示全部组件（verified）：判据是所有组件 `IsHidden(False)=False`。"""
    from ..verified import asm_ops
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else asm_ops.show_all_components(doc))
    return _com(_do)


@mcp.tool(name="sw_move_component")
def sw_move_component(delta_x: float = 0.05, part_path: str = "") -> Dict[str, Any]:
    """平移组件（verified，三轴校验 + 临时件清理）。

    用"变换拷贝法"绕开 IMathUtility；`AddComponent5` 的落点有固定偏置，
    所以先量出偏置再校正重插。
    """
    from ..verified import asm_ops
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else asm_ops.move_component(doc, delta_x=delta_x, part_path=part_path))
    return _com(_do)


@mcp.tool(name="sw_explode_assembly")
def sw_explode_assembly() -> Dict[str, Any]:
    """自动爆炸（verified）：判据是爆炸视图数 +1。

    注意 `AutoExplode` 在 pywin32 下是**属性**，读取即触发。
    """
    from ..verified import asm_ops
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else asm_ops.explode_assembly(doc))
    return _com(_do)


@mcp.tool(name="sw_sketch_construction")
def sw_sketch_construction(plane: str = "前视基准面", length: float = 0.02) -> Dict[str, Any]:
    """草图构造线（verified）：判据是 ConstructionGeometry 开关 True→False 往返成功。"""
    from ..verified import sketch
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else sketch.construction(doc, plane=plane, length=length))
    return _com(_do)


@mcp.tool(name="sw_sketch_text")
def sw_sketch_text(text: str, x: float = 0.0, y: float = 0.0,
                   plane: str = "前视基准面") -> Dict[str, Any]:
    """草图文字（verified）：判据是字形轮廓线段增加，或能读回文字。"""
    from ..verified import sketch
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else sketch.sketch_text(doc, text=text, x=x, y=y, plane=plane))
    return _com(_do)


@mcp.tool(name="sw_add_sketch_constraint")
def sw_add_sketch_constraint(constraint: str = "sgHORIZONTAL",
                             plane: str = "前视基准面") -> Dict[str, Any]:
    """草图约束（verified）：判据是约束数 +1 **或**端点被真正拉平（几何证据）。"""
    from ..verified import sketch
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else sketch.sketch_constraint(doc, constraint=constraint, plane=plane))
    return _com(_do)


@mcp.tool(name="sw_activate_display_state")
def sw_activate_display_state(name: str = "") -> Dict[str, Any]:
    """激活显示状态（verified）。文档没有显示状态时返回 note 而不是假装成功。"""
    from ..verified import model
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else model.activate_display_state(doc, name=name))
    return _com(_do)


@mcp.tool(name="sw_list_materials")
def sw_list_materials(name_filter: str = "", limit: int = 20) -> Dict[str, Any]:
    """列材料库（verified）：**不打开 SolidWorks**，直接解析 `.sldmat`。

    本机实测 3 库 / 29 分类 / 474 材料。为什么走 XML：类型库里 202 个含 material 的方法
    没有一个能枚举材料库。
    """
    from ..verified import model
    return _com(lambda: model.list_materials(name_filter=name_filter, limit=limit))


@mcp.tool(name="sw_bounding_box")
def sw_bounding_box() -> Dict[str, Any]:
    """实体包围盒（verified）：每个实体输出 min/max/尺寸（mm）。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return {"ok": False, "error": "没有打开的文档"} if doc is None else part.bounding_box(doc)
    return _com(_do)


@mcp.tool(name="sw_screenshot")
def sw_screenshot(out_path: str, width: int = 1200, height: int = 800) -> Dict[str, Any]:
    """存 BMP 位图（verified）。PhotoView 无 COM 接口，`SaveBMP` 是等价物。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else part.screenshot(doc, out_path, width, height))
    return _com(_do)


@mcp.tool(name="sw_shell")
def sw_shell(thickness: float = 0.002, face_index: int = -1) -> Dict[str, Any]:
    """抽壳（verified）：`face_index=-1` 自动选最大面；判据是面数翻倍（实测 7→14）。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else part.shell(doc, thickness, face_index))
    return _com(_do)


@mcp.tool(name="sw_split_line")
def sw_split_line() -> Dict[str, Any]:
    """分割线（verified）：先试零参 `InsertSplitLineSil`，再试 `InsertSplitLineProject`。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return {"ok": False, "error": "没有打开的文档"} if doc is None else part.split_line(doc)
    return _com(_do)


@mcp.tool(name="sw_thicken_surface")
def sw_thicken_surface(thickness: float = 0.002) -> Dict[str, Any]:
    """曲面加厚（verified）：判据是出现 `Thicken` 特征。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else part.thicken_surface(doc, thickness))
    return _com(_do)


@mcp.tool(name="sw_offset_surface")
def sw_offset_surface(distance: float = 0.002) -> Dict[str, Any]:
    """曲面偏移（verified）：判据是曲面实体数 +1。"""
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else part.offset_surface(doc, distance))
    return _com(_do)


@mcp.tool(name="sw_pattern_feature")
def sw_pattern_feature(kind: str = "linear", count: int = 3,
                       spacing: float = 0.02, angle_deg: float = 120.0) -> Dict[str, Any]:
    """**特征**阵列（verified）。注意：组件阵列请用 `sw_pattern_component`。

    标记与组件阵列相反：特征 mark=4、方向 mark=1。
    """
    from ..verified import part
    def _do():
        doc = _doc(_app())
        return ({"ok": False, "error": "没有打开的文档"} if doc is None
                else part.pattern_feature(doc, kind=kind, count=count,
                                          spacing=spacing, angle_deg=angle_deg))
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
