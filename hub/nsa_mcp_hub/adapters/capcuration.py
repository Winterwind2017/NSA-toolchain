"""策展清单（P1–P4）：哪些能力值得单独变成一个任务级工具。

原则：
* **按"agent 真的会用它干活"挑**，不是按能力表顺序全上；
* 负例、纯探针（env/lisp/ae）、以及"只有我们自己调试才用"的能力**不上**，
  仍可通过 `*_run_capability` 调用（保留逃生口）；
* 每个 kit 目标 40–60 个任务工具（对齐 CAD-Agent-Hub 的 40/55/55）。

改这里等于改工具表面：加一条就多一个工具，删一条工具就消失（能力本身还在）。
"""

from __future__ import annotations

# ── acad：58 条能力里挑 49 条 ────────────────────────────────────────
# 不上：block.short_attributes（负例）、env.sysvar / env.dimstyle（探针）、
#       lisp.execute（逃生口）、ae.db / pid.symbol / plc.build（专用）、
#       dim.fit_code（内部细节）
ACAD: tuple = (
    # 几何 8
    "geom.line", "geom.circle", "geom.arc", "geom.polyline", "geom.rect",
    "geom.ellipse", "geom.spline", "geom.hatch",
    # 文字 3
    "text.single", "text.mtext", "text.style",
    # 标注 10
    "dim.linear", "dim.aligned", "dim.diametric", "dim.radial", "dim.angular",
    "dim.ordinate", "dim.arc", "dim.baseline", "dim.continuous", "dim.tolerance",
    # 形位公差 / 符号 6
    "gdt.tolerance", "symbol.roughness", "symbol.weld", "symbol.centerline",
    "symbol.centermark", "symbol.balloon",
    # 表格 3
    "table.bom", "table.grid", "table.chinese",
    # 块 2
    "block.define", "block.insert_with_attributes",
    # 图框 / 布局 2
    "frame.titleblock", "layout.multipage",
    # 图层 3
    "layer.create", "layer.set_current", "layer.snapshot",
    # 实体 / 布尔 6
    "solid.primitive", "solid.extrude", "boolean.union", "boolean.subtract",
    "boolean.intersect", "boolean.section_slice",
    # 视图 2
    "view.zoom", "projection.orthographic",
    # 导出 4
    "export.dwg", "export.dxf", "export.pdf", "export.pdf_multipage",
    # 文档生命周期 2（2026-11-04 新增：新建/关闭图纸，用完即关，不碰用户图纸）
    "doc.new", "doc.close",
)

# ── nx：146 条能力里挑 58 条（建模主链路 + 量测 + 出图 + 导出）─────────
NX: tuple = (
    # 零件 / 基准 4
    "part.new", "datum.plane", "datum.axis", "part.inch",
    # 实体 8
    "block.create", "block.two_bodies", "cylinder.create", "solid.cone",
    "solid.sphere", "solid.move_body", "solid.delete_face", "solid.trim_body",
    # 布尔 6
    "boolean.union", "boolean.subtract", "boolean.intersect",
    "boolean.two_tools", "boolean.unite_three", "boolean.subtract_retain",
    # 特征 9
    "extrude.rect", "extrude.ring", "feature.hole", "feature.rib",
    "feature.chamfer", "feature.edge_blend", "feature.pattern_linear",
    "feature.text", "feature.sweep_guide",
    # 草图 6
    "sketch.rect", "sketch.extrude", "sketch.circle_extrude",
    "sketch.constraint", "sketch.horizontal", "sketch.dimension",
    # 量测 5
    "measure.mass", "measure.distance", "measure.faces_two",
    "measure.face_area", "measure.perimeter",
    # 检查 5
    "body.topo", "inspect.body_state", "inspect.face_types",
    "inspect.edge_count", "inspect.body_type",
    # 装配 5
    "asm.two_components", "asm.three_components", "asm.add_component",
    "asm.component_names", "asm.constraint_refs",
    # 制图 4
    "drawing.base_view", "drawing.projected_view", "drawing.sheet_a4",
    "drawing.dimension",
    # 导出 8
    "export.step", "export.step_ap214", "export.iges", "export.dxf",
    "export.dwg", "export.stl", "export.parasolid", "export.acis",
    # 文件 1
    "file.save_copy",
)

# ── gx：42 条能力里挑 30 条（工程/程序/检查/编译/标签/结构体）───────────
GX: tuple = (
    # 工程 7
    "project.new", "project.new_rcpu", "project.new_fx5s", "project.new_language",
    "project.save", "project.reopen", "project.check",
    # 程序 12
    "program.rcpu_roundtrip", "program.paste_st", "program.read_st",
    "program.import_xml", "program.import_fb", "program.import_fb_instance",
    "program.import_fb_params", "program.multi_programs",
    "program.read_st", "program.paste_st",
    # 检查 8
    "project.meta", "project.diff", "inspect.programs", "inspect.ladder",
    "inspect.devices", "inspect.devices_rcpu", "inspect.source_map", "inspect.mil",
    # 编译 5
    "build.convert_all", "build.program_check", "build.error_messages",
    "build.error_detail", "build.locate_error_line",
    # 标签 / 结构体 6
    "label.import_xml", "label.multi_type", "datatype.import",
    "datatype.member_var", "datatype.custom_members", "datatype.struct_array",
    # XML 生成 / 批量 3
    "xmlgen.manual_template", "batch.projects", "batch.new_projects",
)


# ── codesys：16 条命令全部工具化（P4）─────────────────────────────────
CODESYS: tuple = (
    "project.info", "tree", "devices", "execute", "find", "libs",
    "add-lib", "export-xml", "import-xml", "archive", "task", "members",
    "symbols", "textlist", "clean", "save-as",
)

# 只保留这些能力级别（None 表示不过滤）。留给以后按等级收敛工具面用。
def level_ok(level: str) -> bool:
    return True
