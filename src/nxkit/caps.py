"""能力登记表：每条能力 = id + 动作 + 期望读数 + 层级。

`action` 是 `nxkit.runtime.actions` 里的函数名；`expect` 是宿主侧判据要比对的
读数（浮点带容差）。这里**不写实现**，实现只在 runtime 里，避免两处漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLOCK = {"length": 100.0, "width": 50.0, "height": 20.0}


FAMILY_LICENSE: dict[str, str] = {
    "part": "gateway",
    "solid": "solid_modeling",
    "boolean": "solid_modeling",
    "curve": "solid_modeling",
    "feature": "solid_modeling",
    "sketch": "solid_modeling",
    "surface": "solid_modeling",
    "drawing": "drafting",
    "assembly": "assemblies",
    "attr": "gateway",
    "measure": "gateway",
    "inspect": "gateway",
    "export": "gateway",
    "file": "gateway",
}

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

    @property
    def license(self) -> str | None:
        """这条能力需要的 NX feature（按家族）。"""
        return FAMILY_LICENSE.get(self.family)


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
        expect={"body_count": 2, "volume_mm3": 108000.0}, reopen=True),
    Cap("boolean.subtract_retain", "boolean", "求差并保留工具体（2 实体 / 100000）",
        "boolean_subtract_retain", "L1–L3",
        params={}, expect={"body_count": 2,
                           "volume_mm3": {"min": 105000.0, "max": 107500.0},
                           "body_count_reopened": 2},
        reopen=True),
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
        reopen=True),
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
                "volume_mm3": 50000.0, "area_mm2": 13000.0}, reopen=True),

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
                "volume_mm3": 42000.0, "faces": 10}, reopen=True),

    Cap("feature.chamfer", "feature", "一条边倒角 5 mm", "chamfer_one", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": 7,
                "volume_mm3": {"min": 98000.0, "max": 100000.0}}, reopen=True),

    Cap("feature.edge_blend", "feature", "一条边圆角 R5", "edge_blend_one", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": 7,
                "volume_mm3": {"min": 98000.0, "max": 100000.0}}, reopen=True),

    Cap("feature.pattern_linear", "feature", "沿 X 阵列 3 个（间距 120）", "pattern_linear", "L1–L3",
        params={},
        expect={"body_count": 3, "volume_mm3": 300000.0}, reopen=True),

    Cap("feature.pocket", "feature", "块上挖 40×20 通槽", "feature_pocket", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 84000.0}, reopen=True),
    Cap("feature.hole_cyl", "feature", "块上钻 Ø20 通孔", "feature_hole_cyl", "L1–L3",
        params={},
        expect={"body_count": 1, "volume_mm3": 93716.81495770694}, reopen=True),

    Cap("export.acis", "export", "导出 ACIS (.sat)", "export_acis", "L1–L2",
        params={}, expect={"export_ok": True,
                           "export_bytes": {"min": 100.0, "max": 100000000.0}},
        reopen=False),

    Cap("curve.ellipse", "curve", "椭圆（长半轴 50 / 短半轴 25）", "curve_ellipse", "L1–L3",
        params={}, expect={"ellipse_major": 50.0, "ellipse_minor": 25.0},
        reopen=False),
    Cap("attr.on_body", "attr", "实体上写字符串属性", "attr_on_body", "L2",
        params={}, expect={"body_attr": "v1", "body_count": 1,
                           "body_attr_reopened": "v1"}, reopen=True),

    Cap("measure.face_area", "measure", "六面面积和/周长", "measure_face_area", "L3",
        params={},
        expect={"faces": 6, "total_face_area": 16000.0,
                           "total_face_area_reopened": {"min": 15990.0, "max": 16010.0}},
        reopen=True),
    Cap("solid.cone", "solid", "Ø40×30 圆锥", "solid_cone", "L1–L3",
        params={"diameter": 40.0, "height": 30.0},
        expect={"body_count": 1, "volume_mm3": 12566.370614359172},
        reopen=True),
    Cap("solid.sphere", "solid", "Ø40 球", "solid_sphere", "L1–L3",
        params={"diameter": 40.0},
        expect={"body_count": 1, "volume_mm3": 33510.32163829112},
        reopen=True),

    Cap("feature.pattern_grid", "feature", "2×2 矩形阵列", "pattern_grid", "L1–L3",
        params={}, expect={"body_count": 4, "volume_mm3": 400000.0}, reopen=True),
    Cap("feature.pattern_circular", "feature", "绕 Z 圆周阵列 4 个", "pattern_circular", "L1–L3",
        params={}, expect={"body_count": 4, "volume_mm3": 400000.0}, reopen=True),

    Cap("export.step_ap203", "export", "导出 STEP AP203", "export_step_ap203", "L1–L2",
        params={}, expect={"export_ok": True,
                           "export_head": "ISO-10303-21"}, reopen=False),
    Cap("attr.on_feature", "attr", "特征上写字符串属性", "attr_on_feature", "L2",
        params={}, expect={"feature_attr": "f1", "feature_name": "Block(0)"},
        reopen=False),

    Cap("feature.chamfer_multi", "feature", "四条边同时倒角 5 mm", "chamfer_multi", "L1–L3",
        params={},
        expect={"body_count": 1, "faces": {"min": 10.0, "max": 12.0},
                "volume_mm3": {"min": 94000.0, "max": 100000.0}}, reopen=True),


    Cap("boolean.two_tools", "boolean", "一次减去两个工具体", "boolean_two_tools", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 84000.0}, reopen=True),
    Cap("feature.hole_array", "feature", "四个 Ø20 通孔阵列", "hole_array", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": 74867.25849365017}, reopen=True),


    Cap("feature.shell", "feature", "块抽壳 2 mm（封闭空腔）", "feature_shell", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 28000.0, "max": 30000.0}},
        reopen=True),

    Cap("sketch.rect", "sketch", "XY 平面草图 + 4 条线", "sketch_rect", "L1–L2",
        params={}, expect={"sketches": 1, "activated": True, "lines_added": 4,
                           "curves": {"min": 4.0, "max": 8.0}},
        reopen=False),

    Cap("sketch.extrude", "sketch", "草图 4 线拉伸 10 → 50000", "sketch_extrude", "L1–L3",
        params={}, expect={"sketches": 1, "body_count": 1,
                           "volume_mm3": 50000.0}, reopen=True),

    Cap("sketch.circle_extrude", "sketch", "草图整圆拉伸 30 → 37699.11", "sketch_circle_extrude", "L1–L3",
        params={}, expect={"sketches": 1, "body_count": 1,
                           "volume_mm3": 37699.11184307752}, reopen=True),

    Cap("feature.pocket_blind", "feature", "盲槽 40×20 深 10", "feature_pocket_blind", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 92000.0}, reopen=True),
    Cap("feature.hole_blind", "feature", "盲孔 Ø20 深 10", "feature_hole_blind", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": 96858.40734641021}, reopen=True),

    Cap("drawing.view_scale", "drawing", "视图比例 1:2（缩放正好是自动的一半）",
        "drawing_view_scale", "L1–L2",
        params={}, expect={"view_created": True, "ratio_ok": True},
        reopen=False),
    Cap("drawing.second_sheet", "drawing", "插两张图（A3 + A4）",
        "drawing_second_sheet", "L1–L2",
        params={}, expect={"current": "S2", "current_height": 210.0,
                           "current_width": 297.0},
        reopen=False),
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
        reopen=True),
    Cap("feature.edge_blend_all", "feature", "全边圆角 R3", "edge_blend_all", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 94000.0, "max": 100000.0}},
        reopen=True),

    Cap("measure.face_single", "measure", "最大面的面积/周长", "measure_face_single", "L3",
        params={}, expect={"face_area_max": 5000.0, "face_perimeter_max": 300.0},
        reopen=False),
    Cap("feature.chamfer_edge", "feature", "单边倒角 5 mm（另一条边）", "chamfer_edge", "L1–L3",
        params={}, expect={"body_count": 1, "faces": 7,
                           "volume_mm3": {"min": 98500.0, "max": 100000.0}},
        reopen=True),


    Cap("surface.bounded_plane", "surface", "4 条线建有界平面片体", "surface_bounded_plane", "L1–L2",
        params={}, expect={"body_count": 1, "faces": 1,
                           "sheet_count_reopened": 1}, reopen=True),


    Cap("feature.spring", "feature", "沿螺旋线做 Ø10 弹簧", "feature_spring", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 28000.0, "max": 33000.0}},
        reopen=True),
    Cap("feature.tube", "feature", "沿直线做 Ø20 管（实体）", "feature_tube", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 30000.0, "max": 33000.0}},
        reopen=True),


    Cap("curve.helix", "curve", "螺旋线 Ø40 / 螺距 20 / 3 圈", "curve_helix", "L1–L2",
        params={}, expect={"helix_ok": True, "entity_count": 1}, reopen=False),
    Cap("curve.hyperbola", "curve", "双曲线（半实轴 50 / 半虚轴 25）", "curve_hyperbola", "L1–L3",
        params={}, expect={"semi_transverse": 50.0, "semi_conjugate": 25.0},
        reopen=False),
    Cap("curve.parabola", "curve", "抛物线（焦准距 20）", "curve_parabola", "L1–L3",
        params={}, expect={"focal_length": 20.0}, reopen=False),


    Cap("boolean.intersect_two", "boolean", "一次交两个工具体（交工具并集 12000）",
        "boolean_intersect_two", "L1–L3",
        params={}, expect={"body_count": 1, "volume_mm3": 12000.0}, reopen=True),

    Cap("inspect.body_type", "inspect", "实体/片体判定", "inspect_body_type", "L1–L2",
        params={}, expect={"solid_is_solid": True, "solid_is_sheet": False,
                           "sheet_is_sheet": True, "sheet_is_solid": False},
        reopen=False),

    Cap("feature.hole_csk", "feature", "沉头孔（Ø20 通 + Ø30 深 5）", "feature_hole_csk", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 91700.0, "max": 91800.0}},
        reopen=True),
    Cap("solid.cone_frustum", "solid", "圆台（底 Ø40 / 顶 Ø20 / 高 30）",
        "solid_cone_frustum", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 21900.0, "max": 22100.0}},
        reopen=True),

    Cap("asm.four_components", "assembly", "装配插 4 个组件", "asm_four_components", "L1–L2",
        params={}, expect={"components": 4}, reopen=False),
    Cap("asm.nested", "assembly", "子装配 + 零件（外层 2 节点）", "asm_nested", "L1–L2",
        params={}, expect={"components": 2}, reopen=False),

    Cap("feature.boss", "feature", "圆柱凸台 Ø20×10（并集）", "feature_boss", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 103000.0, "max": 103300.0}},
        reopen=True),

    Cap("feature.extrude_taper", "feature", "拉伸 10 带 5° 拔模", "feature_extrude_taper", "L1–L3",
        params={}, expect={"body_count": 1, "faces": 6,
                           "volume_mm3": {"min": 48600.0, "max": 48800.0}},
        reopen=True),
    Cap("feature.cross_hole", "feature", "横向 Ø20 通孔（管道求差）", "feature_cross_hole", "L1–L3",
        params={}, expect={"volume_mm3": {"min": 68500.0, "max": 68700.0}},
        reopen=True),
    Cap("feature.offset_face", "feature", "六面偏置 5 mm（110×60×30）", "feature_offset_face", "L1–L3",
        params={}, expect={"volume_mm3": {"min": 197000.0, "max": 199000.0}},
        reopen=True),
    Cap("feature.stack_blocks", "feature", "两块叠加并集（115000）", "feature_stack_blocks", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 114500.0, "max": 115500.0}},
        reopen=True),
    Cap("attr.double", "attr", "实数属性 3.25 读回", "attr_double", "L2",
        params={}, expect={"double_attr": 3.25}, reopen=False),
    Cap("attr.logical", "attr", "布尔属性 True 读回", "attr_logical", "L2",
        params={}, expect={"logical_attr": True}, reopen=False),
    Cap("sketch.constraint", "sketch", "两条线加重合约束", "sketch_constraint", "L1–L2",
        params={}, expect={"coincidence_ok": True, "inferred": False},
        reopen=False),
    Cap("sketch.horizontal", "sketch", "水平约束", "sketch_constraint_kind", "L1–L2",
        params={"kind": "horizontal"},
        expect={"con_ok": True, "inferred": False, "geom_count": 1}, reopen=False),
    Cap("sketch.vertical", "sketch", "竖直约束", "sketch_constraint_kind", "L1–L2",
        params={"kind": "vertical"},
        expect={"con_ok": True, "inferred": False, "geom_count": 1}, reopen=False),
    Cap("sketch.equal_length", "sketch", "等长约束", "sketch_constraint_kind", "L1–L2",
        params={"kind": "equal"},
        expect={"con_ok": True, "geom_count": 2}, reopen=False),
    Cap("sketch.perpendicular", "sketch", "垂直约束", "sketch_constraint_kind", "L1–L2",
        params={"kind": "perpendicular"},
        expect={"con_ok": True, "geom_count": 2}, reopen=False),
    Cap("sketch.dimension", "sketch", "整圆直径尺寸 50", "sketch_dimension", "L1–L2",
        params={}, expect={"dim_ok": True, "expr_value": 50.0}, reopen=False),
    Cap("sketch.fixed", "sketch", "固定约束", "sketch_fixed", "L1–L2",
        params={}, expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("sketch.collinear", "sketch", "共线约束", "sketch_constraint_extra", "L1–L2",
        params={"kind": "collinear"},
        expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("sketch.concentric", "sketch", "同心约束", "sketch_constraint_extra", "L1–L2",
        params={"kind": "concentric"},
        expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("sketch.midpoint", "sketch", "中点约束", "sketch_constraint_extra", "L1–L2",
        params={"kind": "midpoint"},
        expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("sketch.parallel", "sketch", "平行约束", "sketch_constraint_pair", "L1–L2",
        params={"kind": "parallel"},
        expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("sketch.equal_radius", "sketch", "等半径约束", "sketch_constraint_pair", "L1–L2",
        params={"kind": "equal_radius"},
        expect={"con_ok": True, "inferred": False}, reopen=False),
    Cap("drawing.sheet_a2", "drawing", "A2 图幅 594×420", "drawing_sheet_size", "L1–L2",
        params={"size": "A2"},
        expect={"sheet_height": 420.0, "sheet_width": 594.0}, reopen=False),
    Cap("drawing.sheet_a1", "drawing", "A1 图幅 841×594", "drawing_sheet_size", "L1–L2",
        params={"size": "A1"},
        expect={"sheet_height": 594.0, "sheet_width": 841.0}, reopen=False),
    Cap("drawing.sheet_a0", "drawing", "A0 图幅 1189×841", "drawing_sheet_size", "L1–L2",
        params={"size": "A0"},
        expect={"sheet_height": 841.0, "sheet_width": 1189.0}, reopen=False),
    Cap("sketch.tangent", "sketch", "相切约束", "sketch_tangent", "L1–L2",
        params={}, expect={"con_ok": True}, reopen=False),
    Cap("drawing.sheet_ansi_a", "drawing", "ANSI A 图幅 8.5×11 in", "drawing_sheet_size", "L1–L2",
        params={"size": "A"},
        expect={"sheet_height": 8.5, "sheet_width": 11.0}, reopen=False),
    Cap("drawing.sheet_ansi_b", "drawing", "ANSI B 图幅 11×17 in", "drawing_sheet_size", "L1–L2",
        params={"size": "B"},
        expect={"sheet_height": 11.0, "sheet_width": 17.0}, reopen=False),
    Cap("drawing.sheet_ansi_c", "drawing", "ANSI C 图幅 17×22 in", "drawing_sheet_size", "L1–L2",
        params={"size": "C"},
        expect={"sheet_height": 17.0, "sheet_width": 22.0}, reopen=False),
    Cap("attr.delete", "attr", "属性删除后读回为空", "attr_delete", "L2",
        params={}, expect={"before": "abc", "deleted": True}, reopen=False),
    Cap("attr.update", "attr", "属性覆写为 new", "attr_update", "L2",
        params={}, expect={"value": "new"}, reopen=False),
    Cap("part.inch", "part", "英制部件（4×2×1 in 块，体积 8 in³）", "part_inch", "L1–L3",
        params={}, expect={"units_inch": True, "body_count": 1,
                           "volume_mm3": {"min": 7.9, "max": 8.1}}, reopen=True),
    Cap("export.step_ap214", "export", "AP214 STEP", "export_step_ap214", "L1–L2",
        params={}, expect={"export_ok": True, "has_iso_header": True,
                           "has_automotive_schema": True}, reopen=False),
    Cap("export.parasolid", "export", "Parasolid X_T", "export_parasolid", "L1–L2",
        params={}, expect={"export_ok": True, "head_ok": True}, reopen=False),
    Cap("measure.faces_two", "measure", "只量两个大面（面积 10000）", "measure_faces_two", "L2–L3",
        params={}, expect={"picked": 2,
                           "two_face_area": {"min": 9990.0, "max": 10010.0}},
        reopen=False),
    Cap("measure.distance", "measure", "两个大面之间距离 20", "measure_distance", "L2–L3",
        params={}, expect={"measured": 20.0, "faces_used": 2}, reopen=False),
    Cap("feature.thicken", "feature", "有界平面加厚 5 mm（实体体积 25000）",
        "feature_thicken2", "L1–L3",
        params={}, expect={"solid_count": 1,
                           "volume_mm3": {"min": 24800.0, "max": 25200.0}},
        reopen=True),
    Cap("solid.scale", "solid", "整体缩放 2 倍（体积 800000）", "solid_scale", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 790000.0, "max": 810000.0}},
        reopen=True),
    Cap("feature.mirror", "feature", "以面为镜像平面镜像（2 实体 / 200000）",
        "feature_mirror_face", "L1–L3",
        params={}, expect={"body_count": 2,
                           "volume_mm3": {"min": 199000.0, "max": 201000.0}},
        reopen=True),
    Cap("asm.five_components", "assembly", "装配插 5 个组件", "asm_five_components", "L1–L2",
        params={}, expect={"components": 5}, reopen=False),
    Cap("asm.component_names", "assembly", "组件名保留（AAA/BBB/CCC）", "asm_component_names", "L1–L2",
        params={}, expect={"names": "AAA,BBB,CCC", "name_count": 3}, reopen=False),
    Cap("file.save_copy", "file", "另存副本并重开验证", "file_save_copy", "L1–L4",
        params={}, expect={"copy_exists": True, "copy_body_count": 1,
                           "copy_volume": 100000.0}, reopen=False),
    Cap("attr.count", "attr", "写 3 个属性后数标题", "attr_count", "L2",
        params={}, expect={"title_count": 3}, reopen=False),
    Cap("boolean.unite_three", "boolean", "三体并集（C 在 A 内）", "boolean_unite_three", "L1–L4",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 114500.0, "max": 115500.0}},
        reopen=True),
    Cap("feature.shell_volume", "feature", "抽壳 2 mm 后体积 29344", "feature_shell_volume", "L1–L3",
        params={}, expect={"body_count": 1,
                           "volume_mm3": {"min": 29200.0, "max": 29500.0}},
        reopen=True),
    Cap("attr.on_face", "attr", "属性挂在面上", "attr_on_face", "L2",
        params={}, expect={"face_attr": "x1", "body_attr_empty": True},
        reopen=False),
    Cap("sketch.linear_dim", "sketch", "两线间竖直尺寸 40", "sketch_linear_dim", "L1–L2",
        params={}, expect={"dim_ok": True, "expr_value": 40.0}, reopen=False),
    Cap("asm.constraint_refs", "assembly", "建贴合约束并挂两个面参考",
        "asm_constraint_touch", "L1–L2",
        params={}, expect={"con_ok": True, "ref_count": 2}, reopen=False),
)

def licenses() -> list[tuple[str, str]]:
    """(cap_id, license) 列表，供许可证预检用。"""
    return [(c.id, c.license) for c in CAPS if c.license]


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
