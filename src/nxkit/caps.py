"""能力登记表：每条能力 = id + 动作 + 期望读数 + 层级。

`action` 是 `nxkit.runtime.actions` 里的函数名；`expect` 是宿主侧判据要比对的
读数（浮点带容差）。这里**不写实现**，实现只在 runtime 里，避免两处漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLOCK = {"length": 100.0, "width": 50.0, "height": 20.0}


@dataclass(frozen=True)
class Cap:
    id: str
    family: str
    title: str
    action: str
    level: str
    params: dict = field(default_factory=dict)
    expect: dict = field(default_factory=dict)
    reopen: bool = True


CAPS: tuple[Cap, ...] = (
    Cap("part.new", "part", "新建毫米部件", "part_new", "L1",
        params={"name": "nxkit_part"},
        expect={"part_name_ok": True, "body_count": 0, "units_mm": True}, reopen=False),
    Cap("block.create", "solid", "建 100×50×20 块", "block_create", "L1–L4",
        params=dict(BLOCK),
        expect={"body_count": 1, "faces": 6, "edges": 12,
                "volume_mm3": 100000.0, "area_mm2": 16000.0}),
    Cap("block.two_bodies", "solid", "同一部件两个块（实体数=2）", "block_two", "L1–L4",
        params={"offset_x": 50.0},
        expect={"body_count": 2, "volume_mm3": 108000.0}, reopen=False),
    Cap("boolean.subtract", "boolean", "A−B（重叠 10×50×20）", "boolean_subtract", "L1–L4",
        params={"offset_x": 50.0},
        expect={"body_count": 1, "volume_mm3": 92000.0,
                "body_count_reopened": 1}),
    
    Cap("boolean.union", "boolean", "A∪B", "boolean_union", "L1–L4",
        params={"offset_x": 50.0},
        expect={"body_count": 1, "volume_mm3": 100000.0,
                "body_count_reopened": 1}),
    
    Cap("boolean.intersect", "boolean", "A∩B（10×50×20）", "boolean_intersect", "L1–L4",
        params={"offset_x": 50.0},
        expect={"body_count": 1, "volume_mm3": 8000.0,
                "body_count_reopened": 1}),
    
    Cap("cylinder.create", "solid", "建 Ø40×30 圆柱", "cylinder_create", "L1–L4",
        params={"diameter": 40.0, "height": 30.0},
        expect={"body_count": 1, "faces": 3,
                "volume_mm3": 37699.11184307752}),
    Cap("measure.mass", "measure", "质量属性：体积/面积/重心", "measure_mass", "L3",
        params=dict(BLOCK),
        expect={"volume_mm3": 100000.0, "area_mm2": 16000.0},
        reopen=False),
    Cap("body.topo", "inspect", "拓扑计数：面 6 / 边 12 / 顶点 8", "body_topo", "L1–L3",
        params=dict(BLOCK),
        expect={"faces": 6, "edges": 12}, reopen=False),
    Cap("file.roundtrip", "file", "存盘→重开→复测体积", "file_roundtrip", "L4",
        params=dict(BLOCK),
        expect={"volume_mm3": 100000.0, "volume_reopened": 100000.0}),

    Cap("curve.line", "curve", "两点直线（长度 100）", "curve_line", "L1–L3",
        params={"dx": 100.0, "dy": 0.0, "dz": 0.0},
        expect={"length": 100.0, "start": [0.0, 0.0, 0.0],
                "end": [100.0, 0.0, 0.0]}, reopen=False),
    Cap("curve.arc", "curve", "整圆（R25，周长 50π）", "curve_arc", "L1–L3",
        params={"radius": 25.0},
        expect={"radius": 25.0, "circumference": 157.07963267948966},
        reopen=False),
    Cap("attr.string", "attr", "字符串属性（重开仍在）", "attr_string", "L2–L4",
        params={"title": "NXKIT_STR", "value": "hello-nx"},
        expect={"attr_str": "hello-nx", "attr_after_reopen": "hello-nx"}),
    Cap("attr.int", "attr", "整数属性", "attr_int", "L2",
        params={"title": "NXKIT_INT", "value": 42},
        expect={"attr_int": 42}, reopen=False),

    Cap("extrude.rect", "feature", "矩形截面拉伸（100×50×10）", "extrude_rect", "L1–L4",
        params={"length": 100.0, "width": 50.0, "distance": 10.0},
        expect={"body_count": 1, "faces": 6, "edges": 12,
                "volume_mm3": 50000.0, "area_mm2": 13000.0}, reopen=False),

    Cap("asm.add_component", "assembly", "装配插入 1 个组件", "asm_add_component", "L1–L2",
        params={}, expect={"components": 1}, reopen=False),
    Cap("asm.two_components", "assembly", "装配插入 2 个组件并存盘", "asm_two_components", "L1–L4",
        params={}, expect={"components": 2}),

    Cap("export.step", "export", "导出 STEP（ISO-10303-21）", "export_step", "L1–L3",
        params={}, expect={"export_head": "ISO-10303-21"}, reopen=False),
    Cap("export.iges", "export", "导出 IGES", "export_iges", "L1–L3",
        params={}, expect={"igs": True}, reopen=False),

    Cap("drawing.sheet", "drawing", "插入 A3 图纸页（1:1，第一角）", "drawing_sheet", "L1–L2",
        params={"name": "S1"},
        expect={"sheet_created": True, "sheet_height": 297.0,
                "sheet_width": 420.0}, reopen=False),

    Cap("drawing.base_view", "drawing", "A3 图纸 + Front 基础视图", "drawing_base_view", "L1–L3",
        params={"model_view": "Front"},
        expect={"view_created": True, "model_view_used": "Front"}, reopen=False),

    Cap("extrude.ring", "feature", "带内孔截面拉伸（外框−内框）", "extrude_ring", "L1–L3",
        params={},
        expect={"sections": 1, "body_count": 1,
                "volume_mm3": 42000.0, "faces": 10}, reopen=False),

    Cap("feature.chamfer", "feature", "一条边倒角 5 mm", "chamfer_one", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": 7,
                "volume_mm3": {"min": 98000.0, "max": 100000.0}}, reopen=False),

    Cap("feature.edge_blend", "feature", "一条边圆角 R5", "edge_blend_one", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": 7,
                "volume_mm3": {"min": 98000.0, "max": 100000.0}}, reopen=False),

    Cap("feature.pattern_linear", "feature", "沿 X 阵列 3 个（间距 120）", "pattern_linear", "L1–L3",
        params={},
        expect={"body_count": 3, "volume_mm3": 300000.0}, reopen=False),

    Cap("feature.pocket", "feature", "块上挖 40×20 通槽", "feature_pocket", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 84000.0}, reopen=False),
    Cap("feature.hole_cyl", "feature", "块上钻 Ø20 通孔", "feature_hole_cyl", "L1–L3",
        params={},
        expect={"body_count": 1, "volume_mm3": 93716.81495770694}, reopen=False),

    Cap("export.acis", "export", "导出 ACIS (.sat)", "export_acis", "L1–L2",
        params={}, expect={"export_ok": True,
                           "export_bytes": {"min": 100.0, "max": 100000000.0}},
        reopen=False),

    Cap("curve.ellipse", "curve", "椭圆（长半轴 50 / 短半轴 25）", "curve_ellipse", "L1–L3",
        params={}, expect={"ellipse_major": 50.0, "ellipse_minor": 25.0},
        reopen=False),
    Cap("attr.on_body", "attr", "实体上写字符串属性", "attr_on_body", "L2",
        params={}, expect={"body_attr": "v1", "body_count": 1}, reopen=False),

    Cap("measure.face_area", "measure", "六面面积和/周长", "measure_face_area", "L3",
        params={},
        expect={"faces": 6, "total_face_area": 16000.0}, reopen=False),
    Cap("solid.cone", "solid", "Ø40×30 圆锥", "solid_cone", "L1–L3",
        params={"diameter": 40.0, "height": 30.0},
        expect={"body_count": 1, "volume_mm3": 12566.370614359172},
        reopen=False),
    Cap("solid.sphere", "solid", "Ø40 球", "solid_sphere", "L1–L3",
        params={"diameter": 40.0},
        expect={"body_count": 1, "volume_mm3": 33510.32163829112},
        reopen=False),

    Cap("feature.pattern_grid", "feature", "2×2 矩形阵列", "pattern_grid", "L1–L3",
        params={}, expect={"body_count": 4, "volume_mm3": 400000.0}, reopen=False),
    Cap("feature.pattern_circular", "feature", "绕 Z 圆周阵列 4 个", "pattern_circular", "L1–L3",
        params={}, expect={"body_count": 4, "volume_mm3": 400000.0}, reopen=False),

    Cap("export.step_ap203", "export", "导出 STEP AP203", "export_step_ap203", "L1–L2",
        params={}, expect={"export_ok": True,
                           "export_head": "ISO-10303-21"}, reopen=False),
    Cap("attr.on_feature", "attr", "特征上写字符串属性", "attr_on_feature", "L2",
        params={}, expect={"feature_attr": "f1", "feature_name": "Block(0)"},
        reopen=False),

    Cap("feature.chamfer_multi", "feature", "四条边同时倒角 5 mm", "chamfer_multi", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": {"min": 10.0, "max": 12.0},
                "volume_mm3": {"min": 94000.0, "max": 100000.0}}, reopen=False),


    Cap("boolean.two_tools", "boolean", "一次减去两个工具体", "boolean_two_tools", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 84000.0}, reopen=False),
    Cap("feature.hole_array", "feature", "四个 Ø20 通孔阵列", "hole_array", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": 74867.25849365017}, reopen=False),


    Cap("feature.shell", "feature", "块抽壳 2 mm（封闭空腔）", "feature_shell", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 28000.0, "max": 30000.0}},
        reopen=False),

    Cap("sketch.rect", "sketch", "XY 平面草图 + 4 条线", "sketch_rect", "L1–L2",
        params={}, expect={"sketches": 1, "activated": True, "lines_added": 4,
                           "curves": {"min": 4.0, "max": 8.0}},
        reopen=False),

    Cap("sketch.extrude", "sketch", "草图 4 线拉伸 10 → 50000", "sketch_extrude", "L1–L3",
        params={}, expect={"sketches": 1, "body_count": 1,
                           "volume_mm3": 50000.0}, reopen=False),

    Cap("sketch.circle_extrude", "sketch", "草图整圆拉伸 30 → 37699.11", "sketch_circle_extrude", "L1–L3",
        params={}, expect={"sketches": 1, "body_count": 1,
                           "volume_mm3": 37699.11184307752}, reopen=False),

    Cap("feature.pocket_blind", "feature", "盲槽 40×20 深 10", "feature_pocket_blind", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 92000.0}, reopen=False),
    Cap("feature.hole_blind", "feature", "盲孔 Ø20 深 10", "feature_hole_blind", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": 96858.40734641021}, reopen=False),

    Cap("drawing.sheet_a4", "drawing", "A4 图纸页（297×210）", "drawing_sheet_size", "L1–L2",
        params={"size": "A4"},
        expect={"sheet_created": True, "sheet_height": 210.0, "sheet_width": 297.0},
        reopen=False),
    Cap("drawing.view_isometric", "drawing", "等轴测基准视图", "drawing_view_named", "L1–L2",
        params={"model_view": "Isometric"},
        expect={"view_created": True, "view_name": "Isometric@1"}, reopen=False),

    Cap("asm.three_components", "assembly", "装配插 3 个组件", "asm_three_components", "L1–L2",
        params={}, expect={"components": 3}, reopen=False),

    Cap("export.stl", "export", "导出 STL", "export_stl", "L1–L2",
        params={}, expect={"export_ok": True,
                           "export_bytes": {"min": 100.0, "max": 100000000.0}},
        reopen=False),

    Cap("feature.revolve", "feature", "矩形绕 Z 转 360°（圆柱）", "feature_revolve", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 37600.0, "max": 37800.0}},
        reopen=False),
    Cap("feature.edge_blend_all", "feature", "全边圆角 R3", "edge_blend_all", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 94000.0, "max": 100000.0}},
        reopen=False),

    Cap("measure.face_single", "measure", "最大面的面积/周长", "measure_face_single", "L3",
        params={}, expect={"face_area_max": 5000.0, "face_perimeter_max": 300.0},
        reopen=False),
    Cap("feature.chamfer_edge", "feature", "单边倒角 5 mm（另一条边）", "chamfer_edge", "L1–L3",
        params={}, expect={"body_count": 1, "faces": 7,
                           "volume_mm3": {"min": 99000.0, "max": 100000.0}},
        reopen=False),


    Cap("surface.bounded_plane", "surface", "4 条线建有界平面片体", "surface_bounded_plane", "L1–L2",
        params={}, expect={"body_count": 1, "faces": 1}, reopen=False),

)

BY_ID: dict[str, Cap] = {c.id: c for c in CAPS}
FAMILIES: tuple[str, ...] = tuple(sorted({c.family for c in CAPS}))


def get(cap_id: str) -> Cap:
    try:
        return BY_ID[cap_id]
    except KeyError:
        raise KeyError("未知能力 %r；可用：%s" % (cap_id, ", ".join(sorted(BY_ID))))


def list_caps(family: str | None = None) -> list[Cap]:
    if family:
        return [c for c in CAPS if c.family == family]
    return list(CAPS)


def cases() -> list[dict]:
    return [{"id": c.id, "params": dict(c.params)} for c in CAPS]
