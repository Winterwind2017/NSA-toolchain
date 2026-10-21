"""能力表：把"怎么画（build/）"和"怎么证明（judges/）"接成可执行的能力。

这是内核的**唯一事实来源**之一：CLI、MCP、真机测试都从这里取能力，避免
"测试一套、CLI 一套"的漂移。

每个 :class:`Cap`：

    id       与 `docs/registry.yaml` 的能力 id 同名
    build    (doc, ctx) -> None，动作；参数从 `ctx["params"]` 读
    judge    (rb, ctx) -> verdict，判据；同样从 `ctx["params"]` / `ctx["artifacts"]` 读
    params   默认参数（CLI 可覆盖）
    status   覆盖 registry 状态（默认沿用 registry）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .build import ae as b_ae
from .build import block_table as b_bt
from .build import boolean as b_bool
from .build import dim as b_dim
from .build import envvars as b_env
from .build import export as b_export
from .build import frame as b_frame
from .build import gdt as b_gdt
from .build import geom as b_geom
from .build import layer as b_layer
from .build import lisp as b_lisp
from .build import pid as b_pid
from .build import projection as b_proj
from .build import solid as b_solid
from .build import symbol as b_sym
from .build import table as b_table
from .build import text as b_text
from .build import view as b_view
from .judges import ae as j_ae
from .judges import block_table as j_bt
from .judges import dim as j_dim
from .judges import dim_extra as j_dx
from .judges import env as j_env
from .judges import export as j_export
from .judges import fit as j_fit
from .judges import frame as j_frame
from .judges import generic as j_g
from .judges import geom as j_geom
from .judges import layer as j_layer
from .judges import pid as j_pid
from .judges import projection as j_proj
from .judges import solid as j_solid
from .judges import symbol as j_sym
from .judges import view as j_view
from .judges.case import Case


def _P(ctx: Dict[str, Any], key: str, default: Any = None) -> Any:
    return (ctx.get("params") or {}).get(key, default)


def _A(ctx: Dict[str, Any], key: str, default: Any = None) -> Any:
    return (ctx.get("artifacts") or {}).get(key, default)


@dataclass
class Cap:
    id: str
    family: str
    title: str
    level: str
    build: Callable[[Any, Dict[str, Any]], None]
    judge: Callable[[Any, Dict[str, Any]], Dict[str, Any]]
    params: Dict[str, Any] = field(default_factory=dict)
    wants_reopen: bool = True
    wants_dxf: bool = False
    is_negative: bool = False
    expect: str = "pass"
    expect_fail_checks: Tuple[str, ...] = ()
    status: Optional[str] = None
    note: str = ""

    def case(self, overrides: Optional[Dict[str, Any]] = None) -> Case:
        params = {**self.params, **(overrides or {})}

        def build(doc: Any, ctx: Dict[str, Any]) -> None:
            ctx["params"] = dict(params)
            self.build(doc, ctx)

        def judge(rb: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
            ctx = dict(ctx)
            ctx["params"] = dict(params)
            return self.judge(rb, ctx)

        return Case(self.id, self.family, self.title, build, judge,
                    expect=self.expect, is_negative=self.is_negative,
                    expect_fail_checks=self.expect_fail_checks,
                    wants_reopen=self.wants_reopen, wants_dxf=self.wants_dxf,
                    notes=self.note)


# ── 几何 ────────────────────────────────────────────────────────────
def _cap_geom() -> List[Cap]:
    return [
        Cap("geom.line", "geom", "直线：计数/端点/长度/重开", "L1–L4",
            b_geom.build_line,
            lambda rb, ctx: j_geom.judge_line(
                rb, start=_P(ctx, "start"), end=_P(ctx, "end")),
            {"start": (0.0, 0.0, 0.0), "end": (60.0, 0.0, 0.0)}),
        Cap("geom.circle", "geom", "圆：计数/半径/面积=πR²/重开", "L1–L4",
            b_geom.build_circle,
            lambda rb, ctx: j_geom.judge_circle(
                rb, center=_P(ctx, "center"), radius=_P(ctx, "radius")),
            {"center": (10.0, 20.0, 0.0), "radius": 25.0}),
        Cap("geom.arc", "geom", "圆弧：Center/Radius/起止角", "L1–L4",
            b_geom.build_arc,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ARC", object_name="AcDbArc",
                expected={"Center": _P(ctx, "center"),
                          "Radius": _P(ctx, "radius"),
                          "StartAngle": _P(ctx, "start_angle"),
                          "EndAngle": _P(ctx, "end_angle")}),
            {"center": (0.0, 0.0, 0.0), "radius": 10.0,
             "start_angle": 0.0, "end_angle": math.pi / 2}),
        Cap("geom.polyline", "geom", "多段线：顶点/闭合/长度", "L1–L4",
            b_geom.build_polyline,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="LWPOLYLINE", object_name="AcDbPolyline",
                expected={"Closed": bool(_P(ctx, "closed")),
                          "vertices": _P(ctx, "points"),
                          "Length": _P(ctx, "expected_length")}),
            {"points": [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0)],
             "closed": False, "expected_length": 70.0}),
        Cap("geom.rect", "geom", "矩形：闭合/4 顶点/面积", "L1–L4",
            b_geom.build_rect,
            lambda rb, ctx: j_geom.judge_rect(
                rb, corner1=_P(ctx, "corner1"), corner2=_P(ctx, "corner2")),
            {"corner1": (0.0, 0.0), "corner2": (40.0, 30.0)}),
        Cap("geom.ellipse", "geom", "椭圆：长短轴/面积", "L1–L4",
            b_geom.build_ellipse,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ELLIPSE", object_name="AcDbEllipse",
                expected={"Center": _P(ctx, "center"),
                          "MajorRadius": _P(ctx, "major_radius"),
                          "MinorRadius": float(_P(ctx, "major_radius"))
                          * float(_P(ctx, "ratio")),
                          "Area": math.pi * float(_P(ctx, "major_radius"))
                          * float(_P(ctx, "ratio"))
                          * float(_P(ctx, "major_radius"))}),
            {"center": (100.0, 0.0, 0.0), "major_radius": 20.0, "ratio": 0.5}),
        Cap("geom.spline", "geom", "样条：控制点数", "L1–L4",
            b_geom.build_spline,
            lambda rb, ctx: j_geom.judge_spline(
                rb, closed=False,
                min_control_points=len(_P(ctx, "points") or [])),
            {"points": [(0.0, 50.0), (20.0, 60.0), (40.0, 55.0), (60.0, 70.0)]}),
        Cap("geom.hatch", "geom", "填充：ANSI31/面积", "L1–L4",
            b_geom.build_hatch,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="HATCH", object_name="AcDbHatch",
                expected={"PatternName": _P(ctx, "pattern"),
                          "Area": (float(_P(ctx, "corner2")[0])
                                   - float(_P(ctx, "corner1")[0]))
                          * (float(_P(ctx, "corner2")[1])
                             - float(_P(ctx, "corner1")[1]))}),
            {"corner1": (0.0, 100.0), "corner2": (40.0, 130.0),
             "pattern": "ANSI31"}),
    ]


# ── 文字 ────────────────────────────────────────────────────────────
def _cap_text() -> List[Cap]:
    return [
        Cap("text.single", "text", "单行文字：内容/位置/字高", "L1–L4",
            b_text.build_text,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="TEXT", object_name="AcDbText",
                expected={"TextString": _P(ctx, "text"),
                          "InsertionPoint": _P(ctx, "insertion"),
                          "Height": _P(ctx, "height")}),
            {"text": "ACADKIT 文字", "insertion": (0.0, 200.0, 0.0),
             "height": 5.0}),
        Cap("text.mtext", "text", "多行文字：内容/宽度", "L1–L4",
            b_text.build_mtext,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="MTEXT", object_name="AcDbMText",
                expected={"Width": _P(ctx, "width")},
                contains={"TextString": _P(ctx, "text")}),
            {"text": "多行文字 MTEXT", "insertion": (0.0, 220.0, 0.0),
             "width": 80.0}),
        Cap("text.style", "text", "文字样式：新增 + 字体读回", "L2–L4",
            b_text.build_textstyle,
            lambda rb, ctx: j_g.judge_named_table(
                rb, table="textstyles", name=_P(ctx, "name"),
                contains={"FontFile": _P(ctx, "font")}),
            {"name": "CN_STYLE", "font": "SimSun"}),
    ]


# ── 标注 ────────────────────────────────────────────────────────────
def _cap_dim() -> List[Cap]:
    return [
        Cap("dim.linear", "dim", "线性标注：Measurement/文字外侧", "L1–L4",
            b_dim.build_linear,
            lambda rb, ctx: j_dim.judge_linear(
                rb, p1=_P(ctx, "p1")[:2], p2=_P(ctx, "p2")[:2],
                dim_line=_P(ctx, "dim_line")[:2],
                expected=float(_P(ctx, "expected", 60.0))),
            {"p1": (0.0, 0.0, 0.0), "p2": (60.0, 0.0, 0.0),
             "dim_line": (30.0, 10.0, 0.0), "expected": 60.0}),
        Cap("dim.aligned", "dim", "对齐标注：Measurement", "L1–L4",
            b_dim.build_aligned,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ALIGNEDDIMENSION",
                object_name="AcDbAlignedDimension",
                expected={"Measurement": _P(ctx, "expected")}),
            {"p1": (200.0, 0.0, 0.0), "p2": (260.0, 0.0, 0.0),
             "text_pos": (230.0, 10.0, 0.0), "expected": 60.0}),
        Cap("dim.diametric", "dim", "直径标注：Measurement=2R", "L1–L4",
            b_dim.build_diametric,
            lambda rb, ctx: j_dim.judge_diametric(rb, radius=_P(ctx, "radius")),
            {"radius": 25.0, "center": (10.0, 20.0, 0.0)}),
        Cap("dim.radial", "dim", "半径标注：Measurement=R", "L1–L4",
            b_dim.build_radial,
            lambda rb, ctx: j_dim.judge_radial(rb, radius=_P(ctx, "radius")),
            {"radius": 25.0, "center": (10.0, 20.0, 0.0)}),
        Cap("dim.angular", "dim", "角度标注：Measurement=π/2", "L1–L4",
            b_dim.build_angular,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ANGULARDIMENSION",
                object_name="AcDb2LineAngularDimension",
                expected={"Measurement": math.pi / 2}),
            {"vertex": (300.0, 0.0, 0.0), "p1": (320.0, 0.0, 0.0),
             "p2": (300.0, 20.0, 0.0), "text_pos": (310.0, 10.0, 0.0)}),
        Cap("dim.ordinate", "dim", "坐标标注：Measurement=X", "L1–L4",
            b_dim.build_ordinate,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ORDINATEDIMENSION",
                object_name="AcDbOrdinateDimension",
                expected={"Measurement": _P(ctx, "point")[0]}),
            {"point": (350.0, 0.0, 0.0), "leader": (360.0, 10.0, 0.0),
             "use_x": True}),
        Cap("dim.arc", "dim", "弧长标注：Measurement=R·θ", "L1–L4",
            b_dim.build_arc_dim,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ARCDIMENSION", object_name="AcDbArcDimension",
                expected={"Measurement": 20.0 * math.pi / 2}),
            {"center": (400.0, 0.0, 0.0), "start": (420.0, 0.0, 0.0),
             "end": (400.0, 20.0, 0.0), "text_pos": (412.0, 12.0, 0.0)}),
        Cap("dim.baseline", "dim", "基线标注：两条同基 Measurement", "L1–L4",
            b_dim.build_baseline,
            lambda rb, ctx: j_dx.judge_dim_set(
                rb, expected=[40.0, 100.0]),
            {}),
        Cap("dim.continuous", "dim", "连续标注：两段首尾相接且和=总长", "L1–L4",
            b_dim.build_continuous,
            lambda rb, ctx: j_dx.judge_dim_set(
                rb, expected=[40.0, 60.0], total=100.0),
            {}),
        Cap("dim.tolerance", "dim", "尺寸公差：DIMTOL+TextOverride 读回", "L2–L4",
            b_dim.build_tolerance,
            lambda rb, ctx: j_dx.judge_tolerance(
                rb, expected_measurement=60.0,
                expected_override=str(_P(ctx, "override")),
                recorded={**_A(ctx, "tolerance", {}),
                          "upper": _P(ctx, "upper"), "lower": _P(ctx, "lower")}),
            {"upper": 0.02, "lower": 0.01, "override": "60 +0.02/-0.01"}),
        Cap("dim.fit_code", "dim", "配合代号查表（纯 Python）", "L3",
            b_dim.build_fit_code,
            lambda rb, ctx: j_fit.judge_fit_code(),
            {"code": "H7", "nominal": 50.0}, wants_reopen=False),
        Cap("dim.api_missing", "dim", "负例：AddDimLinear 不存在（必须抛错）",
            "负例", b_dim.build_missing_api,
            lambda rb, ctx: j_dim.judge_raised(_A(ctx, "raised"),
                                               expected=("AttributeError",)),
            is_negative=True, wants_reopen=False),
    ]


# ── 形位公差 / 符号 ─────────────────────────────────────────────────
def _cap_gdt_symbol() -> List[Cap]:
    return [
        Cap("gdt.tolerance", "gdt", "形位公差：ACDBFCF + 符号码", "L1–L4",
            b_gdt.build_gdt,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="ACDBFCF", object_name="AcDbFcf",
                expected={"TextString": _P(ctx, "text")}),
            {"text": "{\\Fgdt;n}%%v0.02", "insertion": (0.0, 300.0, 0.0),
             "direction": (1.0, 0.0, 0.0)}),
        Cap("symbol.roughness", "symbol", "粗糙度符号：3 线 + Ra 文字", "L1–L4",
            b_sym.build_roughness,
            lambda rb, ctx: j_sym.judge_roughness(rb),
            {}),
        Cap("symbol.weld", "symbol", "焊接符号：2 线 + 焊缝尺寸", "L1–L4",
            b_sym.build_weld,
            lambda rb, ctx: j_sym.judge_weld(rb, text=str(_P(ctx, "size", "6"))),
            {"size": "6"}),
        Cap("symbol.centerline", "symbol", "中心线：线型 + 两端超出", "L1–L4",
            b_sym.build_centerline,
            lambda rb, ctx: j_sym.judge_centerline(
                rb, length=44.0, linetype=str(_A(ctx, "linetype"))),
            {"start": (0.0, 0.0), "end": (40.0, 0.0), "extend": 2.0}),
        Cap("symbol.centermark", "symbol", "中心标记：十字过圆心", "L1–L4",
            b_sym.build_centermark,
            lambda rb, ctx: j_sym.judge_centermark(
                rb, center=_P(ctx, "center"),
                arm=float(_P(ctx, "radius")) + float(_P(ctx, "gap"))),
            {"center": (0.0, 0.0), "radius": 10.0, "gap": 1.0}),
        Cap("symbol.balloon", "symbol", "序号气泡：MULTILEADER + 序号", "L1–L4",
            b_sym.build_balloon,
            lambda rb, ctx: j_sym.judge_balloon(rb, index=str(_P(ctx, "index"))),
            {"tip": (0.0, 450.0), "text": (30.0, 470.0), "index": "1"}),
    ]


# ── 表格 / 块 / 图框 ────────────────────────────────────────────────
def _cap_table_block_frame() -> List[Cap]:
    return [
        Cap("table.bom", "table", "BOM 表：逐格 + 合计", "L1–L4",
            b_bt.build_table,
            lambda rb, ctx: j_bt.judge_table(
                rb, rows=5, cols=3, cells=b_bt.BOM_CELLS, sum_column=2,
                detail_rows=(2, 3), total_row=4),
            {}),
        Cap("table.grid", "table", "通用网格表：逐格 + 合计", "L1–L4",
            b_table.build_grid_table,
            lambda rb, ctx: j_bt.judge_table(
                rb, rows=5, cols=3, cells=_P(ctx, "cells") or {
                    "0,0": "GRID", "1,0": "NO.", "1,1": "NAME", "1,2": "QTY",
                    "2,0": "1", "2,1": "BRACKET", "2,2": "2",
                    "3,0": "2", "3,1": "PLATE", "3,2": "3",
                    "4,0": "TOTAL", "4,2": "5"},
                sum_column=2, detail_rows=(2, 3), total_row=4),
            {}),
        Cap("table.chinese", "table", "中文表格：CN 样式 + 重开不丢字", "L1–L4",
            b_table.build_cn_table,
            lambda rb, ctx: j_bt.judge_table(
                rb, rows=3, cols=2,
                cells=_P(ctx, "cells") or b_table.CN_CELLS),
            {"style": "CN", "font": "SimSun"}),
        Cap("block.define", "block", "块定义 + 属性定义", "L1–L4",
            b_bt.build_block_define,
            lambda rb, ctx: j_bt.judge_block_define(
                rb, block_name="BOM_MARK",
                attdefs={"PART_NO": "P-001", "MATERIAL": "Q235"},
                entity_types={"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2}),
            {}),
        Cap("block.insert_with_attributes", "block", "块插入 + 属性值", "L1–L4",
            b_bt.build_block_insert,
            lambda rb, ctx: j_bt.judge_block_insert(
                rb, block_name="BOM_MARK",
                attrs={"PART_NO": "P-777", "MATERIAL": "45#"},
                insertion=(100, 0, 0)),
            {}),
        Cap("block.short_attributes", "block", "负例：属性少一个 → 判据必须失败",
            "负例", b_bt.build_block_short,
            lambda rb, ctx: j_bt.judge_block_insert(
                rb, block_name="BOM_MARK",
                attrs={"PART_NO": "P-777", "MATERIAL": "Q235"},
                insertion=(100, 0, 0)),
            expect="fail", expect_fail_checks=("attr_count",)),
        Cap("frame.titleblock", "frame", "A3 图框 + 标题栏 6 属性", "L3–L4",
            b_frame.build_titleblock,
            lambda rb, ctx: j_frame.judge_titleblock(
                rb, width=420.0, height=297.0, attrs=b_frame.TITLE_ATTRS,
                insertion=(420.0 - 178.0, 2.0, 0.0)),
            {}),
        Cap("layout.multipage", "frame", "新建布局 + 视口", "L2–L4",
            b_frame.build_layout,
            lambda rb, ctx: j_frame.judge_layout(
                rb, name=str(_P(ctx, "name")), recorded=_A(ctx, "layout", {})),
            {"name": "SHEET_A", "viewport_w": 200.0, "viewport_h": 150.0}),
    ]


# ── 图层 / 环境 ─────────────────────────────────────────────────────
def _cap_layer_env() -> List[Cap]:
    return [
        Cap("layer.create", "layer", "建图层：Name/Color 读回", "L2–L4",
            b_layer.build_layer_create,
            lambda rb, ctx: j_g.judge_named_table(
                rb, table="layers", name=_P(ctx, "name"),
                expected={"Color": int(_P(ctx, "color"))}),
            {"name": "01_OUTLINE", "color": 3}),
        Cap("layer.set_current", "layer", "设当前层 + 新实体落层", "L2–L4",
            b_layer.build_layer_set_current,
            lambda rb, ctx: j_layer.judge_layer_current(
                rb, name=_P(ctx, "name")),
            {"name": "02_CENTER", "color": 4}),
        Cap("layer.snapshot", "layer", "图层状态快照：属性级保存→改→恢复", "L3–L4",
            b_layer.build_layer_snapshot,
            lambda rb, ctx: j_layer.judge_layer_snapshot(
                rb, recorded=_A(ctx, "snapshot", {})),
            {"name": "04_SNAP"}),
        Cap("env.sysvar", "env", "系统变量：设置/读回/还原", "L2",
            b_env.build_sysvar,
            lambda rb, ctx: j_env.judge_sysvar(
                _A(ctx, "sysvar", {}), name=_P(ctx, "name"),
                expected=_P(ctx, "value")),
            {"name": "DIMTXT", "value": 3.5}, wants_reopen=False),
        Cap("env.dimstyle", "env", "标注样式：ActiveDimStyle + DIMTXT", "L2",
            b_dim.build_dimstyle,
            lambda rb, ctx: j_env.judge_dimstyle(
                rb, name=_P(ctx, "name"), height=float(_P(ctx, "dimtxt")),
                reopen=False),
            {"name": "ACADKIT_DIM", "dimtxt": 3.5}, wants_reopen=False),
    ]


# ── 3D / 布尔 / 视图 / LISP ────────────────────────────────────────
def _cap_solid() -> List[Cap]:
    sphere = 4.0 / 3.0 * math.pi * 10 ** 3
    return [
        Cap("solid.primitive", "solid", "基本体：box/cylinder/sphere 体积", "L1–L4",
            b_solid.build_primitives,
            lambda rb, ctx: j_solid.judge_solids(
                rb, expected=[40.0 * 20.0 * 10.0, math.pi * 10 ** 2 * 20.0,
                              sphere]),
            {}),
        Cap("solid.extrude", "solid", "拉伸：体积 = 轮廓面积 × 高度", "L1–L4",
            b_solid.build_extrude,
            lambda rb, ctx: j_solid.judge_solids(
                rb, expected=[40.0 * 30.0 * 10.0]),
            {}),
        Cap("boolean.union", "boolean", "并集：2→1，V=10000", "L1–L4",
            b_bool.build_union,
            lambda rb, ctx: j_solid.judge_boolean(rb, expected_volume=10000.0),
            {}),
        Cap("boolean.subtract", "boolean", "差集：2→1，V=6000", "L1–L4",
            b_bool.build_subtract,
            lambda rb, ctx: j_solid.judge_boolean(rb, expected_volume=6000.0),
            {}),
        Cap("boolean.intersect", "boolean", "交集：2→1，V=2000", "L1–L4",
            b_bool.build_intersect,
            lambda rb, ctx: j_solid.judge_boolean(rb, expected_volume=2000.0),
            {}),
        Cap("boolean.section_slice", "boolean", "SLICE：两块体积之和=原体积",
            "L3–L4", b_bool.build_slice,
            lambda rb, ctx: j_solid.judge_slice(rb, expected_total=8000.0),
            {}),
    ]


def _cap_view_lisp() -> List[Cap]:
    return [
        Cap("view.zoom", "view", "ZoomExtents：视图包住几何", "L3",
            b_view.build_zoom_extents,
            lambda rb, ctx: j_view.judge_zoom(
                rb, center=_P(ctx, "center"), radius=float(_P(ctx, "radius"))),
            {"center": (500.0, 500.0), "radius": 100.0}, wants_reopen=False),
        Cap("projection.orthographic", "view",
            "三视图投影：CSG→front/top/left（可见/隐藏/轴线分层）", "L1–L4",
            b_proj.build_projection,
            lambda rb, ctx: j_proj.judge_projection(
                rb, recorded=_A(ctx, "projection", {})),
            {}),
        Cap("lisp.execute", "lisp", "命令行执行 LISP（不加载文件）", "L1–L4",
            b_lisp.build_lisp_circle,
            lambda rb, ctx: j_g.judge_new_entity(
                rb, type_name="CIRCLE", object_name="AcDbCircle",
                expected={"Center": list(_P(ctx, "center")) + [0.0],
                          "Radius": _P(ctx, "radius")}),
            {"center": (800.0, 0.0), "radius": 12.0}),
        Cap("pid.symbol", "pid", "P&ID 符号：闸阀/泵/仪表气泡（程序化画）", "L1–L4",
            b_pid.build_pid_symbols,
            lambda rb, ctx: j_pid.judge_pid(rb, recorded=_A(ctx, "pid", {})),
            {}),
        Cap("ae.db", "ae", "Electrical 元件库：只读打开 + 数表数行 + 哈希不变",
            "L0–L2",
            b_ae.build_ae_db,
            lambda rb, ctx: j_ae.judge_ae_db(_A(ctx, "ae_db", {})),
            {}, wants_reopen=False),
        Cap("plc.build", "plc", "PLC 模块图：规格取自 ace_plc.mdb + 程序化绘制",
            "L1–L4",
            b_ae.build_plc_module,
            lambda rb, ctx: j_ae.judge_plc(rb, recorded=_A(ctx, "plc", {})),
            {}),
    ]


def _cap_export() -> List[Cap]:
    return [
        Cap("export.dwg", "export", "DWG：文件 + AC10 + 重开一致", "L0–L4",
            b_export.build_dwg,
            lambda rb, ctx: j_export.judge_dwg(
                rb, path=_A(ctx, "dwg_path"), since=ctx["started"]),
            {}),
        Cap("export.dxf", "export", "DXF：段 + 族计数 + 重新导入", "L0–L4",
            b_export.build_dxf,
            lambda rb, ctx: j_export.judge_dxf(
                rb, path=_A(ctx, "dxf_path"), since=ctx["started"],
                dxf=_A(ctx, "dxf_info")),
            {}, wants_dxf=True),
        Cap("export.pdf", "export", "PDF：A3 + 非空白", "L0–L3",
            b_export.build_pdf,
            lambda rb, ctx: j_export.judge_pdf(
                rb, path=_A(ctx, "pdf_path"), since=ctx["started"],
                plot=_A(ctx, "plot")),
            {}),
        Cap("export.pdf_multipage", "export",
            "多页 PDF：逐布局出图 + 合并（每页 A3 且有墨）", "L0–L3",
            b_export.build_pdf_multipage,
            lambda rb, ctx: j_export.judge_pdf_multipage(
                rb, path=_A(ctx, "pdf_path"), since=ctx["started"],
                pages=2, recorded=_A(ctx, "multipage", {})),
            {}),
    ]


def _all() -> List[Cap]:
    return (_cap_geom() + _cap_text() + _cap_dim() + _cap_gdt_symbol()
            + _cap_table_block_frame() + _cap_layer_env() + _cap_solid()
            + _cap_view_lisp() + _cap_export())


CAPS: List[Cap] = _all()
BY_ID: Dict[str, Cap] = {c.id: c for c in CAPS}
FAMILIES: Dict[str, List[str]] = {}
for _c in CAPS:
    FAMILIES.setdefault(_c.family, []).append(_c.id)


def cases(only: Optional[Sequence[str]] = None) -> List[Case]:
    caps = CAPS
    if only:
        keys = set(only)
        caps = [c for c in CAPS if c.id in keys or c.family in keys]
    return [c.case() for c in caps]


def get(cap_id: str) -> Cap:
    if cap_id not in BY_ID:
        raise KeyError("没有能力 %r（用 `acadkit list` 看全部）" % cap_id)
    return BY_ID[cap_id]


def build(cap_id: str, doc: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """只跑动作（给需要"建图但不判"的脚本用）。返回 ctx['artifacts']。"""
    cap = get(cap_id)
    ctx: Dict[str, Any] = {"params": {**cap.params, **(params or {})},
                           "artifacts": {}, "notes": []}
    cap.build(doc, ctx)
    return ctx


def implemented_ids() -> List[str]:
    return sorted(BY_ID)


BUILDERS = {c.id: c.build for c in CAPS}
