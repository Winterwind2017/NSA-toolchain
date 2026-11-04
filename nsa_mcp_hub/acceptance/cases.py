"""验收用例：SolidWorks / NX / AutoCAD 三家各一组。

SolidWorks 的用例跑在**临时副本**上（`NSA_MCP_HUB_SW_FIXTURE` 可覆盖默认夹具），
NX / AutoCAD 的用例走各自 kit 的 `*_run_capability`，本来就自带几何判据。
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SW_FIXTURE = os.environ.get(
    "NSA_MCP_HUB_SW_FIXTURE", r"C:\Users\yuche\Desktop\450隔音罩1-B2.SLDPRT")


# ----------------------------------------------------------------- SolidWorks
def _sw_attach():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("SldWorks.Application")


def _sw_title(model) -> str:
    value = model.GetTitle
    return value if isinstance(value, str) else value()


def _solidworks_running() -> bool:
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
        return "SLDWORKS.exe" in (out.stdout or "")
    except Exception:                              # noqa: BLE001
        return False


def sw_setup() -> dict:
    if not os.path.isfile(SW_FIXTURE):
        print("  [warn] 找不到 SolidWorks 夹具：%s" % SW_FIXTURE, flush=True)
        return {"available": False, "solidworks": False}
    # 绝不为跑验收去“启动”SolidWorks——没开就跳过，避免制造副作用
    if not _solidworks_running():
        print("  [warn] SolidWorks 没在运行，SolidWorks 组跳过（本套件不会替你启动它）",
              flush=True)
        return {"available": False, "solidworks": False}
    workdir = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_")
    copy_path = os.path.join(workdir, os.path.basename(SW_FIXTURE))
    shutil.copy2(SW_FIXTURE, copy_path)
    try:
        from win32com.client import VARIANT
        import pythoncom
        app = _sw_attach()
        err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        model = app.OpenDoc6(copy_path, 1, 1, "", err, warn)   # 1 = Silent
        if model is None:
            # 这份夹具可能已经开着（上一轮 setup 打开没关）——OpenDoc6 会 return None
            # 且 err=65536。按路径找一下已打开的文档，别再报错。
            model = None
            # 注意：GetDocuments 在晚绑定下是**属性**不是方法（调它会 TypeError）。
            # 而且每轮 setup 的临时目录不同，不能比全路径——比**文件名**即可：
            # 夹具副本是丢弃品，同名开着的那个就是上次留下的。
            wanted = os.path.basename(copy_path).lower()
            docs = app.GetDocuments
            for item in (docs or []):
                try:
                    # 这两个在晚绑定下都是**属性**，加括号会 TypeError
                    path = str(item.GetPathName or "")
                    title = str(item.GetTitle or "")
                    if path and os.path.basename(path).lower() == wanted:
                        model = item
                        break
                    if not path and title.lower() == os.path.splitext(wanted)[0].lower():
                        model = item
                        break
                except Exception:                      # noqa: BLE001
                    continue
        if model is None:
            raise RuntimeError("打开夹具失败（err=%s）" % err.value)
        return {"available": True, "solidworks": True, "workdir": workdir,
                "copy": copy_path, "title": _sw_title(model)}
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def sw_teardown(context: dict) -> None:
    if not context.get("available"):
        return
    try:
        app = _sw_attach()
        for _ in range(10):
            if int(app.GetDocumentCount) == 0:
                break
            docs = app.GetDocuments
            docs = docs() if callable(docs) else docs
            model = docs[0]
            app.CloseDoc(_sw_title(model))       # 不保存：都是副本
    except Exception as exc:                      # noqa: BLE001
        print("  [warn] 关闭文档失败：%s" % exc, flush=True)
    shutil.rmtree(context["workdir"], ignore_errors=True)


def _no_fixture(context: dict) -> bool:
    return not context.get("available")


def _select_args(client):
    """先 inspect 拿 2 个持久引用 token，再拿去选面。"""
    payload = client.call("sw_feature_inspect",
                          {"include_topology": True, "include_tokens": True, "limit": 6})
    topo = ((payload.get("reads") or {}).get("result") or {}).get("topology") or []
    tokens = [t["reference_token"] for t in topo if t.get("reference_token")][:2]
    return {"tokens": tokens}


_FEA_BLOCK = {"version": "1.0", "metadata": {"part_type": "block"}, "features": [
    {"name": "Part", "kind": "new_part", "title": "FEA accept block"},
    {"name": "S1", "kind": "sketch", "plane": "Front Plane",
     "entities": [{"kind": "polyline", "closed": True,
                   "points": [[-50, -25], [50, -25], [50, 25], [-50, 25]]}]},
    {"name": "B1", "kind": "boss_extrude", "sketch": "S1", "depth_mm": 10,
     "merge": False}]}


def _fea_prepare(client):
    """为 FEA 用例铺路：建 100×50×10 方块 → 设材质/约束/力 → 划 20 mm 网格。

    判据链：RunAnalysis=0 且 study.Results 非空（脚本自己校验），
    所以这里任何一步失败都直接抛错，不把"跑过了"当成"有结果"。
    """
    for step, tool, args in (
            ("建块", "sw_execute_feature_graph", {"feature_graph": _FEA_BLOCK}),
            ("setup", "sw_sim_setup", {"restraint_face": 4, "force_face": 5,
                                       "force_n": 100, "material": "AISI 304",
                                       "mesh": False}),
            ("mesh", "sw_sim_mesh", {"size": 0.02, "tol": 0.002})):
        r = client.call(tool, args)
        if not r.get("ok"):
            raise RuntimeError("%s 失败：%s" % (step, (r.get("errors") or ["-"])[0]))
    return {}


SW_CASES = [
    {"id": "sw.inspect.topology", "tool": "sw_feature_inspect",
     "title": "列出特征树 + 拓扑 + token",
     "args": {"include_topology": True, "include_tokens": True, "limit": 20},
     "expect_check_true": ["features_listed", "all_features_named"],
     "skip_if": _no_fixture},

    {"id": "sw.param.thickness", "tool": "sw_set_feature_parameter",
     "title": "板厚 5→8mm，体积应 ×1.6",
     "args": {"feature": "凸台-拉伸1", "parameter": "D1", "value": 8.0,
              "confirm": True},
     "expect_checks": {"value_readback_m": 0.008, "geometry_delta": True},
     "expect_ratio": {"reads.geometry_after.volume_mm3 / reads.geometry_before.volume_mm3": 1.6},
     "skip_if": _no_fixture},

    {"id": "sw.param.fillet", "tool": "sw_set_feature_parameter",
     "title": "圆角 5→3mm，体积微增",
     "args": {"feature": "圆角1", "parameter": "D1", "value": 3.0, "confirm": True},
     "expect_checks": {"value_readback_m": 0.003},
     "expect_check_true": ["applied"],
     "skip_if": _no_fixture},

    {"id": "sw.rollback.before", "tool": "sw_feature_rollback",
     "title": "回滚棒移到 凸台-拉伸1 之前",
     "args": {"location": "before", "feature": "凸台-拉伸1"},
     "expect_checks": {"moved": True}, "skip_if": _no_fixture},

    {"id": "sw.rollback.end", "tool": "sw_feature_rollback",
     "title": "回滚棒归位到 end",
     "args": {"location": "end"},
     "expect_checks": {"moved": True}, "skip_if": _no_fixture},

    {"id": "sw.select.faces", "tool": "sw_select_references",
     "title": "用 2 个 token 选面",
     "prepare": _select_args,
     "expect_check_true": ["tokens_resolved", "selected_count"],
     "skip_if": _no_fixture},

    {"id": "sw.flow.part", "tool": None,
     "title": "SW 剧本：新建零件→矩形草图 40×25→拉伸 20→量体积（判 20000 mm³）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     # 用 lambda 延迟解析：_sw_part_flow 定义在 SW_CASES 之后（模块加载顺序）
     "call": lambda client, context: _sw_part_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.fillet", "tool": None,
     "title": "SW 剧本二：圆 Ø40→拉伸 15→圆角 R2（判体积下降 0–5%）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_fillet_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.inspect", "tool": None,
     "title": "SW 剧本三：块 40×25×10 + 读/视图类 7 个工具（12 步，判 10000 mm³）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_inspect_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.export", "tool": None,
     "title": "SW 剧本四：建块→存盘→导出 STEP/STL（判 ISO-10303-21 与 STL 大小）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_export_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.props", "tool": None,
     "title": "SW 剧本五：倒角/抽壳/自定义属性/配置/材料/重建诊断（14 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_props_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.equations", "tool": None,
     "title": "SW 剧本六：方程/全局变量/镜向/回滚/显示模式（12 步，判 W=40 与 H=10）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_equations_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sketch", "tool": None,
     "title": "SW 剧本七：草图类 10 工具（弧/多边形/椭圆/中心线/偏移/阵列），判体积不变",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.drawing", "tool": None,
     "title": "SW 剧本八：零件→出图→标注→导出 PDF（判 %PDF 头与 >1 KB）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.light.reads", "tool": None,
     "title": "SW 只读 12 连：状态/注册表/文档/索引/模型信息/包围盒（夹具打开时也安全）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_light_reads(client, context)},

    {"id": "sw.flow.surface", "tool": None,
     "title": "SW 剧本九：曲面族（平面区域→加厚→拉伸曲面→偏移曲面，判实体与曲面都存在）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_surface_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.drawing2", "tool": None,
     "title": "SW 剧本十一：IGES 导出 + 出图注释 + 视图旋转 + 导出 PDF/DWG（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing2_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sheet", "tool": None,
     "title": "SW 剧本十：钣金基体法兰 + 展开图信息（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sheet_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.status", "tool": "sw_status",
     "title": "连接状态 + 打开文档数 + 注册表摘要（不建模）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    {"id": "sw.registry", "tool": "sw_registry",
     "title": "工具注册表：哪些真的能用、依据是什么",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    {"id": "sw.sphere.plan", "tool": "sw_sphere_plan",
     "title": "球体图生成器（上游 create_sphere 的图）：3 个特征 + 体积 4/3·π·r³",
     "args": {"diameter_mm": 40.0},
     "expect_ok": True,
     "expect_reads": {"reads.feature_count": 3},
     "expect_check_true": ["feature_count", "volume_formula"],
     "expect_min_checks": 2,
     # 纯计算（不碰 COM）：SolidWorks 没开也要跑
     "no_setup": True,
     "timeout_s": 180},

    # ── 从上游 test_*.py 搬来的判据（纯几何，不需要 SolidWorks 在跑）──
    {"id": "sw.plan.gear", "tool": "sw_gear_involute_plan",
     "title": "上游 test_involute_gear：m2 z20 → 分度 R20 / 外径 R22 / 齿根 R17.5 / 基圆 R18.79",
     "args": {"module_mm": 2, "tooth_count": 20, "pressure_angle_deg": 20,
              "thickness_mm": 10, "bore_diameter_mm": 10},
     "expect_ok": True,
     "expect_reads": {"reads.spec_valid": True, "reads.feature_count": 9,
                      "reads.spec.pitch_radius_mm": 20.0,
                      "reads.spec.outer_radius_mm": 22.0,
                      "reads.spec.root_radius_mm": 17.5,
                      "reads.spec.base_radius_mm": 18.79385241571817},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.gearbox", "tool": "sw_gearbox_plan",
     "title": "上游 test_gearbox：传动比 6.0、两级中心距 60/80",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.metadata.total_ratio": 6.0,
                      "reads.metadata.stage1_center_distance_mm": 60.0,
                      "reads.metadata.stage2_center_distance_mm": 80.0},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.flange", "tool": "sw_part_plan",
     "title": "上游 test_part_generators：法兰 8 孔 → 5 个特征",
     "args": {"part_type": "flange", "parameters": {"outer_diameter_mm": 120,
                                                    "bore_diameter_mm": 40,
                                                    "thickness_mm": 12,
                                                    "bolt_circle_diameter_mm": 90,
                                                    "bolt_hole_diameter_mm": 10,
                                                    "bolt_count": 8}},
     "expect_ok": True,
     "expect_reads": {"reads.part_type": "flange", "reads.feature_count": 5},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.output_shaft", "tool": "sw_output_shaft_plan",
     "title": "上游 test_output_shaft：总长 333、7 段直径 [55,60,65,60,55,50,45]",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.metadata.total_length_mm": 333.0,
                      "reads.feature_count": 12},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.create.sphere.live", "tool": "sw_create_sphere",
     "title": "一步到位（真机）：球 Ø40 → 体积 33510.3 mm³（解析解误差 <0.05%）",
     "args": {"diameter_mm": 40.0, "execute": True},
     "expect_ok": True,
     "expect_check_true": ["executed", "steps_ok"],
     "expect_between": {"reads.execute.body_volume_mm3": [33500.0, 33520.0]},
     "timeout_s": 900},

    {"id": "sw.create.gear", "tool": "sw_create_involute_gear",
     "title": "一步到位封装：齿轮出图（execute=false → 9 个特征；收尾默认关，SW2025 无 FeatureFillet）",
     "args": {"module_mm": 2.0, "tooth_count": 20, "execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 9, "reads.executed": False},
     "expect_check_true": ["graph_built", "feature_names"],
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.create.reducer", "tool": "sw_create_two_stage_reducer",
     "title": "一步到位封装：两级减速器出图（16 特征 + 传动比 6.0 + 中心距 60）",
     "args": {"execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 16, "reads.ratio": 6.0,
                      "reads.center_distance_stage1_mm": 60.0},
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.create.sphere", "tool": "sw_create_sphere",
     "title": "一步到位封装：球体出图 + 解析体积 4/3·π·r³",
     "args": {"diameter_mm": 40.0, "execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 3, "reads.analytic_volume_mm3": 33510.322},
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.graph.block", "tool": "sw_execute_feature_graph",
     "title": "Feature Graph 建块 100×60×20 → 体积 120000",
     "args": {"feature_graph": {"version": "1.0", "metadata": {"part_type": "block"},
                                "features": [
                                    {"name": "Part", "kind": "new_part", "title": "acceptance block"},
                                    {"name": "BlockSketch", "kind": "sketch", "plane": "Front Plane",
                                     "entities": [{"kind": "polyline", "closed": True,
                                                   "points": [[-50, -30], [50, -30], [50, 30], [-50, 30]]}]},
                                    {"name": "BlockBoss", "kind": "boss_extrude",
                                     "sketch": "BlockSketch", "depth_mm": 20, "merge": False}]},
              "expected_volume_mm3": 120000},
     "expect_check_true": ["steps_ok", "volume_matches_expected"],
     "expect_reads": {"reads.body_volume_mm3": 120000},
     "skip_if": _no_fixture},

    {"id": "sw.index.stats", "tool": "swdm_stats",
     "title": "DocumentMgr 索引统计（环境项）",
     "args": {},
     "expect_check_true": ["files_indexed"]},

    {"id": "sw.index.query", "tool": "swdm_query",
     "title": "按扩展名查索引（取 3 条 .sldprt）",
     "args": {"ext": ".sldprt", "limit": 3},
     "expect_check_true": ["output_present"]},

    {"id": "sw.sim.addin", "tool": "sw_sim_addin_check",
     "title": "Simulation 加载项自检（cosworks.dll）",
     "args": {},
     "expect_check_true": ["sim_dll_exists"]},

    # 放在最后：它会新建一个方块文档并留下研究，避免影响前面的用例
    {"id": "sw.fea.solve", "tool": "sw_sim_run",
     "title": "小方块三段式 FEA：20 mm 网格 → 求解 → Results 非空",
     "prepare": _fea_prepare,
     "expect_check_true": ["solve_reported", "results_ready"],
     "timeout_s": 600},

    # ── P5 hub 语义增强的验收（真机，需 SolidWorks 有活动文档）──────────
    {"id": "sw.hub.docs", "tool": "sw_list_documents_dirty",
     "title": "列出文档 + dirty 状态（hub 增强）",
     "args": {}, "expect_check_true": ["doc_count", "active_present"],
     "skip_if": _no_fixture},

    {"id": "sw.hub.inspect", "tool": "sw_inspect_active",
     "title": "当前文档自审查（类型/特征数）",
     "args": {}, "expect_check_true": ["type", "feature_count"],
     "skip_if": _no_fixture},

    {"id": "sw.hub.bbox", "tool": "sw_bounding_box_with_hidden",
     "title": "包围盒（mm，三个方向都 >0）",
     "args": {"include_hidden": False},
     "expect_check_true": ["bodies", "dx_mm", "dy_mm", "dz_mm"],
     "skip_if": _no_fixture},

    {"id": "sw.export.step", "tool": "sw_export_step",
     "title": "导出 STEP（判据：文件头 ISO-10303-21）",
     "args": lambda ctx: {"path": os.path.join(tempfile.gettempdir(),
                                               "nsa_mcp_hub_accept_450.step")},
     "expect_ok": True,
     "skip_if": _no_fixture},
]


# ------------------------------------------------------------------------ NX
NX_CASES = [
    {"id": "nx.status", "tool": "nx_status",
     "title": "NX 环境（run_journal 路径 + 能力数）",
     "args": {},
     "expect_reads": {"reads.cap_count": 146}},

    {"id": "nx.selftest", "tool": "nx_selftest",
     "title": "离线自检：每条能力的动作与判据是否齐全（不开 NX）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    # ── 多步剧本：一条用例覆盖一串工具（快乐路径）──
    {"id": "nx.batch.asm", "tool": None,
     "title": "NX 批量：装配三组件/组件名/约束参考（3 条）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "call": lambda client, context: _nx_batch(client, [
         "nx_asm_three_components", "nx_asm_component_names", "nx_asm_constraint_refs",
     ])},

    {"id": "nx.batch.export_asm", "tool": None,
     "title": "NX 批量：DWG/DXF 导出/另存副本/引导扫掠/修剪实体/投影视图/装配两组件/加组件（8 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_export_dwg", "nx_export_dxf", "nx_file_save_copy", "nx_feature_sweep_guide",
         "nx_solid_trim_body", "nx_drawing_projected_view", "nx_asm_two_components",
         "nx_asm_add_component",
     ])},

    {"id": "nx.batch.boolean", "tool": None,
     "title": "NX 批量：布尔差保留/双工具/三体并/双实体/移动/文字/筋/两面/体类型/Parasolid（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_boolean_subtract_retain", "nx_boolean_two_tools", "nx_boolean_unite_three",
         "nx_block_two_bodies", "nx_solid_move_body", "nx_feature_text", "nx_feature_rib",
         "nx_measure_faces_two", "nx_inspect_body_type", "nx_export_parasolid",
     ])},

    {"id": "nx.batch.solid", "tool": None,
     "title": "NX 批量：圆锥/球/孔/倒角/边倒圆/线性阵列/实体状态/基准面/基准轴/ACIS（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_solid_cone", "nx_solid_sphere", "nx_feature_hole", "nx_feature_chamfer",
         "nx_feature_edge_blend", "nx_feature_pattern_linear", "nx_inspect_body_state",
         "nx_datum_plane", "nx_datum_axis", "nx_export_acis",
     ])},

    {"id": "nx.batch.sketch_drawing", "tool": None,
     "title": "NX 批量：草图约束/水平/尺寸 + A4 图纸/基础视图/尺寸标注（6 条）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _nx_batch(client, [
         "nx_sketch_constraint", "nx_sketch_horizontal", "nx_sketch_dimension",
         "nx_drawing_sheet_a4", "nx_drawing_base_view", "nx_drawing_dimension",
     ])},

    {"id": "nx.batch.export", "tool": None,
     "title": "NX 批量：环形拉伸/整圆拉伸/布尔交/面面积/距离/边数/英制/IGES/STL/STEP-AP214（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_extrude_ring", "nx_sketch_circle_extrude", "nx_boolean_intersect",
         "nx_measure_face_area", "nx_measure_distance", "nx_inspect_edge_count",
         "nx_part_inch", "nx_export_iges", "nx_export_stl", "nx_export_step_ap214",
     ])},

    {"id": "nx.batch.model", "tool": None,
     "title": "NX 批量：拉伸/布尔并/布尔差/块/圆柱/量质量/周长/面类型/拓扑/导出 STEP（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_extrude_rect", "nx_boolean_union", "nx_boolean_subtract",
         "nx_block_create", "nx_cylinder_create", "nx_measure_mass",
         "nx_measure_perimeter", "nx_inspect_face_types", "nx_body_topo",
         "nx_export_step",
     ])},

    {"id": "nx.flow.block", "tool": None, "title": "NX 剧本：新建零件→矩形草图→拉伸→量质量",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _flow(client, [
         ("nx_part_new", {}),
         ("nx_sketch_rect", {}),
         ("nx_sketch_extrude", {}),
         ("nx_measure_mass", {}),
     ])},

    {"id": "nx.flow.inspect", "tool": None,
     "title": "NX 剧本：实体拓扑 + 面积/周长 + 能力清单",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _flow(client, [
         ("nx_body_topo", {}),
         ("nx_measure_face_area", {}),
         ("nx_measure_perimeter", {}),
         ("nx_list_caps", {}),
     ])},

    {"id": "nx.block", "tool": "nx_run_capability",
     "title": "真机建块 100×50×20 → 体积 100000",
     "args": {"ids": ["block.create"]},
     "expect_check_true": ["volume_mm3", "faces", "edges"],
     "expect_min_checks": 3},
]


# ------------------------------------------------------------------------ GX
GX_CASES = [
    {"id": "gx.selftest", "tool": "gx_selftest",
     "title": "离线自检：动作与判据是否齐全（不开 GX Works3）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    {"id": "gx.paste_st", "tool": "gx_run_capability",
     "title": "把 ST 粘进程序并转换（判据：步数 2-200）",
     "args": {"ids": ["program.paste_st"], "keep": True},
     "expect_check_true": ["steps"],
     "expect_min_checks": 1},

    {"id": "gx.convert_all", "tool": "gx_run_capability",
     "title": "全部转换（判据：errors=0 / warnings=0 / stages≥3）",
     "args": {"ids": ["build.convert_all"], "keep": True},
     "expect_checks": {"errors": 0, "warnings": 0},
     "expect_min_checks": 2},
]


# ------------------------------------------------------------------- AutoCAD
ACAD_CASE_TIMEOUT = 120.0


def _acad_com():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("AutoCAD.Application")


def acad_setup() -> dict:
    """验收前把 ATTDIA 关掉。

    实测：`block.insert_with_attributes` 在 ATTDIA=1 时会**卡住不返回**（属性输入对话框
    在等用户点确定）；ATTDIA=0 后 7.9 s 全绿。跑完恢复原值。
    """
    try:
        app = _acad_com()
        # AutoCAD 停在开始页时一个文档都没有，ActiveDocument 会抛
        # "无法获取 Document 对象"；那会把整组误判成环境不可用。
        if int(app.Documents.Count) == 0:
            app.Documents.Add()
        doc = app.ActiveDocument
        saved = {"ATTDIA": doc.GetVariable("ATTDIA"),
                 "FILEDIA": doc.GetVariable("FILEDIA")}
        doc.SetVariable("ATTDIA", 0)
        # FILEDIA=1 时，任何"需要文件名"的动作（Save/SaveAs/打开文件）都会弹模态框，
        # COM 随即一直等到用户点确定 —— 这正是 projection 被误判成"卡 120 s"的来源。
        doc.SetVariable("FILEDIA", 0)
        return {"available": True, "saved": saved}
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] AutoCAD 未就绪（%s），acad 组跳过" % str(exc)[:80], flush=True)
        return {"available": False}


def acad_between(context: dict) -> None:
    """每条用例之间存一次盘，消掉 close 时的"是否保存"提示。"""
    if not context.get("available"):
        return
    try:
        doc = _acad_com().ActiveDocument
        if doc.Saved:
            return
        # 没有 FullName 的图纸（新建未存盘）调 Save() 会走"另存为"，FILEDIA=1 时弹框卡死。
        if not (getattr(doc, "FullName", "") or "").strip():
            return
        doc.Save()
    except Exception:                              # noqa: BLE001
        pass


def acad_teardown(context: dict) -> None:
    if not context.get("available"):
        return
    try:
        app = _acad_com()
        doc = app.ActiveDocument
        # 先恢复原值（含 FILEDIA），再兜底把我调试期改过的一项恢复默认
        for key, value in (context.get("saved") or {}).items():
            doc.SetVariable(key, value)
        doc.SetVariable("CMDECHO", 1)
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] 恢复 AutoCAD 变量失败：%s" % exc, flush=True)


def _acad_missing(context: dict) -> bool:
    return not context.get("available")

ACAD_CASES = [
    {"id": "acad.caps", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_list_caps",
     "title": "几何族能力清单",
     "args": {"family": "geom"},
     "expect_reads": {"reads.total": 8}},

    # 放在最前面：这条要 insert + 读属性，图纸越"脏"越容易碰到保存/属性提示
    {"id": "acad.block.insert", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "块插入 + 属性值读回",
     "args": {"ids": ["block.insert_with_attributes"]},
     "expect_check_true": ["count", "attr_values", "reopen"]},

    {"id": "acad.block.define", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "块定义 + 属性定义",
     "args": {"ids": ["block.define"]},
     "expect_check_true": ["new_block", "attdef_count"]},

    # acad_status 在 AutoCAD 没开时返回 ok=false（真实的"没接上"，不是通过），
    # 所以这条必须依赖 setup 门禁：没开就整组 SKIP，而不是硬判 True。
    {"id": "acad.status", "tool": "acad_status",
     "title": "AutoCAD 环境自检（只附加不启动）",
     "args": {}, "expect_ok": True, "timeout_s": 180},

    {"id": "acad.line", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "真机画 60mm 线 → 长度/重开判据",
     "args": {"ids": ["geom.line"]},
     "expect_check_true": ["length", "count"],
     "expect_min_checks": 5},

    {"id": "acad.circle", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "画 R25 圆 → 半径/面积=πR²/重开",
     "args": {"ids": ["geom.circle"]},
     "expect_check_true": ["count", "type", "geometry", "area", "reopen"],
     "expect_reads": {"reads.details[\"geom.circle\"].radius_mm": 25.0}},

    {"id": "acad.rect", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "画 40×30 矩形 → 闭合/顶点/面积",
     "args": {"ids": ["geom.rect"]},
     "expect_check_true": ["reopen"],
     "expect_min_checks": 4},

    {"id": "acad.dim.linear", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "线性标注 60mm → Measurement 读回",
     "args": {"ids": ["dim.linear"]},
     "expect_check_true": ["measurement", "text_side"],
     "expect_reads": {"reads.details[\"dim.linear\"].measurement_mm": 60.0}},

    {"id": "acad.text.single", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "单行文字 → 内容/位置/字高",
     "args": {"ids": ["text.single"]},
     "expect_min_checks": 3},

    {"id": "acad.layer.create", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "建图层 + Name/Color 读回",
     "args": {"ids": ["layer.create"]},
     "expect_min_checks": 2},

    {"id": "acad.solid.primitive", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "3D 基本体 → 体积判据",
     "args": {"ids": ["solid.primitive"]},
     "expect_min_checks": 3},

    {"id": "acad.solid.extrude", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "3D 拉伸 → 体积 = 面积 × 高",
     "args": {"ids": ["solid.extrude"]},
     "expect_min_checks": 3},

    {"id": "acad.projection", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "三视图投影（front/top/left）",
     "args": {"ids": ["projection.orthographic"]},
     "expect_min_checks": 3},

    {"id": "acad.table.bom", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "BOM 表逐格 + 合计",
     "args": {"ids": ["table.bom"]},
     "expect_min_checks": 3},

    {"id": "acad.export.dxf", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "导出 DXF → 文件/段/重新导入计数",
     "args": {"ids": ["export.dxf"]},
     "expect_check_true": ["file", "sections", "parsed"]},

    {"id": "acad.export.pdf_multipage", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "多页 PDF：逐布局出图（每页 A3 且有墨）",
     "args": {"ids": ["export.pdf_multipage"]},
     "expect_min_checks": 3},
]


# ------------------------------------------------------------------- CODESYS
def _codesys_available(context: dict) -> bool:
    return not context.get("available")


def _codesys_service_alive(state: str) -> bool:
    """state 文件存在 ≠ 服务活着。

    实测（2026-11-03）：CODESYS 关掉后 `service.json` 还留着旧端口，
    setup 直接复用 → 4 条用例全报 `WinError 10061 目标计算机积极拒绝`。
    所以必须真去 connect 一下，连不上就当陈旧状态处理。
    """
    import json
    import socket
    try:
        with open(state, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:                              # noqa: BLE001
        return False
    port = int(data.get("port") or 0)
    if port <= 0:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return True
    except OSError:
        return False


def _codesys_flow(client, context):
    """CODESYS 剧本：project.create（带 device）→ POU 写入/读回 → 编译 → 导出 XML。

    关键实测：POU 路径必须是**全路径** `/PLC/Plc Logic/Application/<名字>`，
    写 `/AcPlay` 会 E_STATE（path segment not found）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_")
    project = os.path.join(work, "ac_play.project")
    xml = os.path.join(work, "export.xml")
    app = "/PLC/Plc Logic/Application"
    pou = app + "/AccPlay"
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccPlay", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_pou_write", {"path": pou, "part": "declaration",
                               "text": "PROGRAM AccPlay\nVAR\n    x : INT;\nEND_VAR\n"}),
        ("codesys_pou_write", {"path": pou, "part": "implementation",
                               "text": "x := x + 1;\n"}),
        ("codesys_pou_read", {"path": pou, "part": "implementation"}),
        ("codesys_app_generate", {}),
        ("codesys_app_status", {}),
        ("codesys_export_xml", {"path": xml, "target": app}),
    ]
    done = []
    impl = ""
    uptodate = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        reads = payload.get("reads") or {}
        inner = reads.get("result") or {}          # codesys 的读数都在 result 里
        if name == "codesys_pou_read":
            impl = str(inner.get("text") or reads.get("text") or "")
        if name == "codesys_app_status":
            uptodate = inner.get("is_uptodate", reads.get("is_uptodate"))
    size = os.path.getsize(xml) if os.path.exists(xml) else 0
    ok_impl = "x := x + 1" in impl
    ok_xml = size > 200
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pou_readback", "got": impl.strip()[:40], "want": "x := x + 1", "ok": ok_impl},
        {"check": "app_uptodate", "got": uptodate, "want": "bool", "ok": uptodate is not None},
        {"check": "xml_bytes", "got": size, "want": ">200", "ok": ok_xml},
    ]
    problems = []
    if not ok_impl:
        problems.append("POU 读回不含目标语句：%r" % impl[:80])
    if not ok_xml:
        problems.append("PLCopenXML 太小/没写：%s B" % size)
    return {"ok": ok_impl and ok_xml,
            "reads": {"steps": done, "pou_text": impl, "is_uptodate": uptodate,
                      "xml_bytes": size, "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_cleanup(client, context):
    """删掉剧本自己的临时目录（里面有 29 MB 归档，不删会堆）。"""
    work = context.get("workdir") if isinstance(context, dict) else None
    if work and os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)


def _codesys_ops_flow(client, context):
    """CODESYS 剧本二：任务/文件夹/改名/保存/另存/归档/搜文本/对象信息（11 步）。

    注：`codesys_symbols_create` 实测 E_SCRIPT（父对象不接受符号配置对象），未纳入。

    全部在临时工程里做；归档产物落在剧本自己的临时目录，cleanup 会删掉。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_ops_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    archive = os.path.join(work, "ac.archive")
    saved = os.path.join(work, "ac_saved.project")
    steps = [
        ("codesys_tasks", {}),
        ("codesys_task_create", {"name": "AccTask", "pous": [app + "/AccPlay"],
                                 "interval": 10, "priority": 5, "unit": "ms"}),
        ("codesys_folder_create", {"parent": app, "name": "AccFolder"}),
        ("codesys_object_rename", {"path": app + "/AccFolder", "name": "AccFolder2"}),
        ("codesys_project_meta", {}),
        ("codesys_libraries", {}),
        ("codesys_object_info", {"path": app + "/AccPlay"}),
        ("codesys_find_text", {"pattern": "x := x + 1", "limit": 3}),
        ("codesys_project_save", {}),
        ("codesys_project_save_as", {"path": saved}),
        ("codesys_project_archive", {"path": archive}),
    ]
    done = []
    matches: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        inner = (payload.get("reads") or {}).get("result") or {}
        if name == "codesys_find_text":
            matches = inner.get("items") or []
    archive_bytes = os.path.getsize(archive) if os.path.exists(archive) else 0
    saved_bytes = os.path.getsize(saved) if os.path.exists(saved) else 0
    ok_find = any("x := x + 1" in str(m.get("text", "")) for m in matches if isinstance(m, dict))
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "find_text", "got": len(matches), "want": ">=1 且含目标语句", "ok": ok_find},
        {"check": "saved_bytes", "got": saved_bytes, "want": ">1000", "ok": saved_bytes > 1000},
        {"check": "archive_bytes", "got": archive_bytes, "want": ">1000", "ok": archive_bytes > 1000},
    ]
    problems = []
    if not ok_find:
        problems.append("find_text 没命中目标语句：%r" % (matches,)[:120])
    if not (saved_bytes > 1000 and archive_bytes > 1000):
        problems.append("另存/归档文件异常：saved=%d archive=%d" % (saved_bytes, archive_bytes))
    return {"ok": ok_find and saved_bytes > 1000 and archive_bytes > 1000,
            "reads": {"steps": done, "matches": matches, "saved_bytes": saved_bytes,
                      "archive_bytes": archive_bytes, "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_extras_flow(client, context):
    """CODESYS 剧本三：POU 成员/持久变量表/库/文本表/原生导出（10 步）。

    实测不可用的两个：`pou.member`（E_SCRIPT 名称无效）、`project.io_export`
    （device 参数要的是树路径不是设备名），都没纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_extras_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    pou = app + "/AccPlay2"
    native = os.path.join(work, "app.export")
    project = os.path.join(work, "ac_extras.project")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccPlay2", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_pou_write", {"path": pou, "part": "declaration",
                               "text": "PROGRAM AccPlay2\nVAR\n    y : INT;\nEND_VAR\n"}),
        ("codesys_pou_members", {"path": pou}),
        ("codesys_pou_persistent", {"name": "PersistVars"}),
        ("codesys_library_add", {"name": "Standard"}),
        ("codesys_textlist_create", {"name": "AccTexts", "languages": ["en", "zh"]}),
        ("codesys_libraries", {}),
        ("codesys_export_native", {"path": native, "target": app}),
        ("codesys_project_meta", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    native_bytes = os.path.getsize(native) if os.path.exists(native) else 0
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "native_bytes", "got": native_bytes, "want": ">1000", "ok": native_bytes > 1000},
    ]
    return {"ok": native_bytes > 1000, "reads": {"steps": done, "native_bytes": native_bytes,
                                                 "workdir": work},
            "errors": [] if native_bytes > 1000 else ["原生导出太小：%d B" % native_bytes],
            "checks": checks}


def codesys_setup() -> dict:
    """起常驻服务（headless，约 8-10 s）；**确认服务真的应答**才复用。"""
    import json
    import subprocess
    import sys as _sys
    state = os.path.join(os.environ.get("LOCALAPPDATA", ""), "codesyskit", "service.json")
    if os.path.isfile(state) and _codesys_service_alive(state):
        return {"available": True, "started": False}
    if os.path.isfile(state):
        # 陈旧状态：挪到一边，让 start 重新写
        try:
            os.replace(state, state + ".stale")
            print("  [info] CODESYS 服务状态陈旧（端口连不上），已归档并重启服务", flush=True)
        except Exception:                          # noqa: BLE001
            pass
    src = os.environ.get("CODESYSKIT_SRC", r"D:\bililive\codesyskit\src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run([_sys.executable, "-c",
                        "import sys;from codesyskit.cli import main;sys.exit(main(sys.argv[1:]))",
                        "start", "--wait", "180"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, env=env)
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] 起 CODESYS 服务失败：%s" % exc, flush=True)
        return {"available": False}
    ok = os.path.isfile(state) and _codesys_service_alive(state)
    if not ok:
        print("  [warn] CODESYS 服务起不来（state 存在=%s）" % os.path.isfile(state), flush=True)
    return {"available": ok, "started": True}


CODESYS_CASES = [
    {"id": "codesys.ping", "tool": "codesys_ping",
     "title": "常驻服务往返（最轻量的存活判据）",
     "args": {}, "expect_ok": True, "timeout_s": 120},

    {"id": "codesys.flow.extras", "tool": None,
     "title": "CODESYS 剧本三：POU 成员/持久变量/库/文本表/原生导出（10 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_extras_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.ops", "tool": None,
     "title": "CODESYS 剧本二：任务/文件夹/改名/符号/保存/另存/归档/搜文本（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_ops_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.pou", "tool": None,
     "title": "CODESYS 剧本：建带 device 工程 → POU 写入/读回 → 编译 → 导出 PLCopenXML（8 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_flow(client, context)},

    {"id": "codesys.status", "tool": "codesys_status",
     "title": "常驻服务可达 + 版本",
     "args": {},
     "expect_check_true": ["service_reachable", "version_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.create", "tool": "codesys_call",
     "title": "新建工程（写到临时目录）",
     "args": lambda ctx: {"cmd": "project.create",
                          "args": {"path": os.path.join(tempfile.gettempdir(),
                                                        "nsa_mcp_hub_accept_codesys.project")}},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.info", "tool": "codesys_call",
     "title": "读工程信息",
     "args": {"cmd": "project.info"},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.tree", "tool": "codesys_call",
     "title": "读对象树",
     "args": {"cmd": "tree", "args": {"path": "", "depth": 2}},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},
]


# ------------------------------------------------------------------- AutoShop
def _autoshop_missing(context: dict) -> bool:
    return not context.get("available")


def _autoshop_no_project(context: dict) -> bool:
    """没打开工程时没法编译——这是环境问题，不是工具坏了，跳过并说明。"""
    return not context.get("available") or not context.get("project")


def _as_run(*args, timeout=300):
    """跑一次 autoshopkit CLI，返回解析后的 JSON（失败返回 {}）。"""
    import json
    import subprocess
    import sys as _sys
    src = os.environ.get("AUTOSHOPKIT_SRC", r"D:\bililive\autoshopkit\src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    runner = os.path.join(tempfile.gettempdir(), "ash_run.py")
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write("import sys\nfrom autoshopkit.cli import main\nsys.exit(main(sys.argv[1:]))\n")
    try:
        p = subprocess.run([_sys.executable, runner, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except Exception:                              # noqa: BLE001
        return {}
    text = p.stdout or ""
    dec = json.JSONDecoder()
    best = {}
    idx = 0
    while True:
        i = text.find("{", idx)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(text[i:])
            if isinstance(obj, dict):
                best = obj
            idx = i + end
        except Exception:                          # noqa: BLE001
            idx = i + 1
    return best


def _il_program(path: str) -> bool:
    info = _as_run("hcp", "--project", path, timeout=90)
    fields = (info.get("fields") or {})
    return str(fields.get("FileName") or "").upper().endswith(".IL")


def autoshop_setup() -> dict:
    """确保 AutoShop 打开的是**带指令列表(H3U/MAIN.IL)的工程**。

    `apply` 需要 IL 编辑器：H5U 或 MAIN.LD 的工程只有梯形图，`apply` 会报
    `no instruction-list editor`。所以这里主动准备一份 IL 工程副本（不碰用户工程）。
    """
    status = _as_run("status", timeout=120)
    project = str(status.get("project") or "")
    if project:
        hcps = glob.glob(os.path.join(project, "*.hcp"))
        if not hcps or not _il_program(hcps[0]):
            project = ""                           # 不是 IL 工程，换掉
    if project:
        return {"available": True, "project": project, "provisioned": False}

    src = os.environ.get("AUTOSHOP_IL_PROJECT", r"D:\bililive\autoshopkit\sandbox\ilcorpus")
    if not os.path.isdir(src):
        print("  [warn] 找不到 IL 工程样本：%s" % src, flush=True)
        return {"available": False}
    # 先关掉 AutoShop（旧工程占着文件，删不掉也拷不进去），再用**唯一目录**复制
    _as_run("stop", timeout=120)
    time.sleep(3)
    workdir = os.path.join(tempfile.gettempdir(),
                           "nsa_mcp_hub_accept_autoshop_%s" % time.strftime("%H%M%S"))
    shutil.copytree(src, workdir)
    hcps = glob.glob(os.path.join(workdir, "*.hcp"))
    if not hcps:
        print("  [warn] 复制出来的工程里没有 .hcp", flush=True)
        return {"available": False}
    hcp = hcps[0]
    started = _as_run("start", hcp, timeout=300)
    if not started.get("pid"):
        print("  [warn] 启动 AutoShop 失败", flush=True)
        return {"available": False}
    time.sleep(3)
    return {"available": True, "project": workdir, "provisioned": True,
            "hcp": hcp}


def autoshop_between(context: dict) -> None:
    """用例之间如果 AutoShop 被前一条命令带走了（实测 compile/apply 超时或保存后会退出），
    就用同一份工程副本重新拉起来，保证后面的用例仍有环境。"""
    if not context.get("available"):
        return
    status = _as_run("status", timeout=60)
    if status.get("pid"):
        return
    hcp = context.get("hcp")
    if not hcp:
        hcps = glob.glob(os.path.join(context.get("project") or "", "*.hcp"))
        hcp = hcps[0] if hcps else ""
    if not hcp:
        return
    started = _as_run("start", hcp, timeout=300)
    if started.get("pid"):
        print("  [info] AutoShop 已重新拉起（pid=%s）" % started["pid"], flush=True)
        time.sleep(3)


def autoshop_teardown(context: dict) -> None:
    """只清理我们复制的工程；不动用户原来开的工程。"""
    if not context.get("provisioned"):
        return
    _as_run("stop", timeout=120)


def _apply_fixture() -> str:
    """写一份三网 IL 到临时文件，给 apply 用例用。"""
    path = os.path.join(tempfile.gettempdir(), "nsa_mcp_hub_accept_apply.il")
    text = ("//net one\nLD X0\nOUT Y0\n"
            "//net two\nLD X1\nOUT Y1\n"
            "//net three\nLD X2\nOUT Y2\n")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


AUTOSHOP_CASES = [
    {"id": "autoshop.doctor", "tool": "autoshop_doctor",
     "title": "环境自检：工程 / UIA / frida / 编辑器",
     "args": {}, "expect_ok": True, "timeout_s": 180},

    {"id": "autoshop.status", "tool": "autoshop_status",
     "title": "attach 到 AutoShop",
     "args": {},
     "expect_ok": True,
     "skip_if": _autoshop_missing},

    {"id": "autoshop.tree", "tool": "autoshop_tree",
     "title": "导出工程树",
     "args": {},
     "expect_ok": True,
     "skip_if": _autoshop_missing},

    # 编译放在 apply 之前：实测 apply（写 IL + 保存）之后 AutoShop 会退出
    {"id": "autoshop.compile", "tool": "autoshop_compile",
     "title": "全部编译 → 错误数 0",
     "args": {"timeout_s": 45},
     "expect_checks": {"compile_ok": True, "error_lines": 0},
     "timeout_s": 420,
     "skip_if": _autoshop_no_project},

    {"id": "autoshop.apply", "tool": "autoshop_apply",
     "title": "写 IL → 转换 → 编译（readback_ok + 0 错误）",
     "args": lambda ctx: {"file": _apply_fixture(), "doc": "MAIN", "confirm": True},
     "expect_checks": {"compile_errors": 0, "readback_ok": True},
     "expect_check_true": ["bytes_written"],
     "timeout_s": 420,
     "skip_if": _autoshop_no_project},
]


# ── ug（CAD-Agent-Hub 的 NX MCP：CAM / 机床 / 钣金 / 装配约束）────────────
def _ug_no_live_nx(context: dict) -> bool:
    """NX 交互式会话不在时跳过：上游要 socket 桥（start_mcp.py 在 NX 里跑过）。"""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ugraf.exe"],
                             capture_output=True, text=True, timeout=20).stdout
        return "ugraf.exe" not in out.lower()
    except Exception:                                  # noqa: BLE001
        return True


def _ug_cam_recipe(client, context: dict) -> dict:
    """端到端 CAM 配方：新零件 → 零件体/毛坯体 → CAM 设置 → 三条工序各自生成刀路。

    覆盖的是「模板 + 工具面」这条链：工序默认毛坯必须是「毛坯几何体」（改过的
    mill_planar.prt 模板），并且 set_cam_operation_geometry 要给工序自己的毛坯体、
    切削区里要有零件顶面 + 毛坯顶面；平面铣还要 floor_z + 边界曲线。
    任何一环退化（模板被还原、参数没生效），path_exists 会立刻变 false。
    """
    import time as _time

    stamp = _time.strftime("%H%M%S")
    part_name = "nsa_accept_cam_%s.prt" % stamp
    steps = []
    checks = []
    ops = {}

    def call(tool: str, args: dict, label: str, strict: bool = True):
        result = client.call(tool, args)
        steps.append({"step": label, "tool": tool, "ok": bool(result.get("ok"))})
        if not result.get("ok") and strict:
            error = (result.get("errors") or [{}])[0]
            raise RuntimeError("%s 失败：%s" % (label, str(error)[:220]))
        return result

    def top_face(body_index: int):
        data = call("ug_inspect_body_topology", {"body_index": body_index},
                    "topology_%d" % body_index).get("reads") or {}
        for face in data.get("faces") or []:
            normal = face.get("normal") or [0, 0, 0]
            if abs(float(normal[2]) - 1.0) < 1e-6:
                return face.get("stable_id")
        raise RuntimeError("body %d 没有 +Z 顶面" % body_index)

    try:
        # 1. 独立零件：零件体 100×60×20，毛坯体 104×64×24（顶面同为 z=20）
        call("ug_create_part", {"file_name": part_name}, "create_part")
        call("ug_create_block", {"length": 100.0, "width": 60.0, "height": 20.0,
                                 "origin": [0.0, 0.0, 0.0]}, "part_block")
        call("ug_create_block", {"length": 104.0, "width": 64.0, "height": 24.0,
                                 "origin": [-2.0, -2.0, -4.0]}, "blank_block")
        call("ug_initialize_cam_setup", {"template_name": "mill_planar"}, "cam_setup")
        call("ug_create_cam_mill_tool", {"name": "T1_D10", "diameter": 10.0,
                                         "flute_length": 30.0,
                                         "overall_length": 75.0}, "tool")
        call("ug_create_cam_milling_context", {
            "origin": [0.0, 0.0, 20.0],
            "part_body_indices": [0],
            "blank_body_indices": [1],
            "workpiece_name": "MCP_WORKPIECE",
        }, "workpiece")

        part_top = top_face(0)
        blank_top = top_face(1)
        selectors = [
            {"selector": {"stable_id": part_top}, "body_index": 0},
            {"selector": {"stable_id": blank_top}, "body_index": 1},
        ]

        # 2. 三条工序，覆盖腔铣族 / 无壁底面 / 平面铣
        for subtype in ("FLOOR_FACING", "POCKETING", "PLANAR_MILL"):
            name = "ACC_%s" % subtype
            call("ug_create_cam_operation", {
                "name": name,
                "template_subtype": subtype,
                "template_type": "mill_planar",
                "tool_name": "T1_D10",
                "geometry_name": "MCP_WORKPIECE",
            }, "create_%s" % subtype)
            call("ug_set_cam_operation_geometry", {
                "operation_name": name,
                "part_body_indices": [0],
                "blank_body_indices": [1],
                "cut_area_face_selectors": selectors,
                "auto_add_blank_faces": True,
                "floor_z": 0.0,
                "depth_per_cut": 2.0,
            }, "geometry_%s" % subtype)
            generated = call("ug_generate_cam_toolpath", {"operation_names": [name]},
                             "generate_%s" % subtype, strict=False)
            checks.append({"check": "%s.generate_ok" % subtype,
                           "ok": bool(generated.get("ok")),
                           "got": bool(generated.get("ok")), "want": True})

        # 3. 判据：三条都得有刀路
        inspected = call("ug_inspect_cam_operations", {}, "inspect").get("reads") or {}
        for record in inspected.get("operations") or []:
            ops[record.get("name")] = bool(record.get("path_exists"))
        for subtype in ("FLOOR_FACING", "POCKETING", "PLANAR_MILL"):
            name = "ACC_%s" % subtype
            found = ops.get(name, False)
            checks.append({"check": "%s.path_exists" % subtype, "ok": found,
                           "got": found, "want": True})
        return {
            "ok": all(item["ok"] for item in checks),
            "reads": {"part": part_name, "operations": ops,
                      "part_top": part_top, "blank_top": blank_top,
                      "steps": steps},
            "checks": checks,
            "errors": [],
        }
    finally:
        # 收紧现场：关掉验收零件（不存盘），把显示切回原零件
        try:
            client.call("ug_run_python", {"code": (
                "import NXOpen\n"
                "s = NXOpen.Session.GetSession()\n"
                "target = None\n"
                "for p in s.Parts:\n"
                "    if str(p.Leaf).startswith('nsa_accept_cam_'):\n"
                "        target = p\n"
                "        break\n"
                "if target is not None:\n"
                "    target.Close(NXOpen.BasePart.CloseWholeTree.TrueValue,\n"
                "                 NXOpen.BasePart.CloseModified.CloseModified, None)\n"
                "left = [p for p in s.Parts]\n"
                "if left:\n"
                "    try:\n"
                "        s.Parts.SetDisplay(left[0], False, True)\n"
                "    except Exception:\n"
                "        pass\n"
                "result = [str(p.Leaf) for p in s.Parts]\n"
            ), "timeout": 180.0})
        except Exception:                              # noqa: BLE001
            pass


UG_CASES = [
    {"id": "ug.ping", "tool": "ug_ping",
     "title": "NX 桥连通性（进程/零件/桥版本）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 120,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.cam.capabilities", "tool": "ug_get_cam_capabilities",
     "title": "CAM 能力自报（模块/许可/可用操作）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 180,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.cam.recipe", "call": _ug_cam_recipe,
     "title": "CAM 端到端配方：新零件 → 三种工序各自生成刀路（path_exists）",
     "expect_check_true": ["FLOOR_FACING.path_exists", "POCKETING.path_exists",
                           "PLANAR_MILL.path_exists", "FLOOR_FACING.generate_ok",
                           "POCKETING.generate_ok", "PLANAR_MILL.generate_ok"],
     "expect_min_checks": 6,
     "timeout_s": 900,
     "skip_if": _ug_no_live_nx},
]

# ── eplan（CAD-Agent-Hub 的 EPLAN 2.9 MCP：电气设计 / 审图）──────────────
def codesys_setup() -> dict:
    """CODESYS 是否"空着"——project.create 会关掉当前工程，绝不能关用户的。

    只有当前没有工程、或当前工程在临时目录里（我们自己的），才允许跑剧本。
    """
    from nsa_mcp_hub.acceptance.harness import McpClient
    client = McpClient("nsa_mcp_hub.servers.codesys_mcp")
    try:
        payload = client.call("codesys_projects", {})
    finally:
        client.close()
    result = (payload.get("reads") or {}).get("result") or {}
    path = str((result.get("primary") or {}).get("path") or "")
    temp = os.environ.get("TEMP", "").lower()
    ours = (not path) or (temp and path.lower().startswith(temp))
    if not ours:
        print("  [warn] CODESYS 里有非临时工程，剧本跳过（不会关你的工程）：%s" % path,
              flush=True)
    return {"available": True, "codesys_free": bool(ours), "project": path}


def nx_setup() -> dict:
    """nxkit 的 `nx_run_capability` 会自己拉起 NX，所以不能靠"进程在不在"判断。

    实测教训：用 tasklist 找 ugraf.exe 判 nx，结果 NX 明明能跑（4 个能力全 True），
    判成 False → 剧本被误判成"该拒绝"，反过来 FAIL。所以这里直接放行。
    """
    return {"available": True, "nx": True}


def _close_unsaved_docs(client):
    """关掉所有"没路径"的文档——那是剧本自己新建的临时零件，不是用户的文件。"""
    closed = []
    reads = client.call("sw_list_open_documents", {}).get("reads") or {}
    for item in reads.get("documents") or []:
        if item.get("path"):
            continue
        try:
            client.call("sw_close_document", {"title": item.get("title")})
            closed.append(item.get("title"))
        except Exception:                              # noqa: BLE001
            pass
    return closed


def _sw_part_flow(client, context):
    """SolidWorks 剧本：新建零件 → 前视基准面矩形 40×25 → 拉伸 20 → 量体积。

    单位坑：swkit 的草图坐标是 **mm**（第一次按米传 0.04/0.025 直接失败）。
    判据：6 步全 ok 且体积 = 40×25×20 = 20000 mm³ = 2e-05 m³。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 20}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    last = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        last = payload
    volume = (last.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 2e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 2e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积不符：%r（期望 2e-05 m³ = 20000 mm³）" % volume],
            "checks": checks}


def _sw_fillet_flow(client, context):
    """SW 剧本二：圆 Ø40 → 拉伸 15 → 圆角 R2。

    判据：7 步全 ok，且圆角让体积**下降**（实测 18849.56 → 18638.63 mm³，约 -1.12%）。
    为什么不带切除：swkit 的 `sw_cut_extrude` 在本机 SW2025 上建出的是空特征
    （体积不变、features +1），实测 `flip_side` 两种都无效——已记入待修，剧本绕开它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_circle", {"cx": 0.0, "cy": 0.0, "radius": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 15}),
        ("sw_fillet", {"radius": 2}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    fillet = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_fillet":
            fillet = payload.get("reads") or {}
    before = fillet.get("volume_before_mm3")
    after = fillet.get("volume_after_mm3")
    dropped = (before and after and 0 < (before - after) / before < 0.05)
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "fillet_edges", "got": fillet.get("edges_selected"), "want": ">0",
         "ok": bool(fillet.get("edges_selected"))},
        {"check": "volume_dropped", "got": round((before - after), 3) if before and after else None,
         "want": ">0 且 <5%", "ok": bool(dropped)},
    ]
    return {"ok": bool(dropped), "reads": {"steps": done,
                                           "volume_before_mm3": before,
                                           "volume_after_mm3": after},
            "errors": [] if dropped else ["圆角没有让体积下降：%r → %r" % (before, after)],
            "checks": checks}


def _sw_inspect_flow(client, context):
    """SW 剧本三：建块 40×25×10，然后把"读/视图"类工具跑一遍（12 步一条）。

    判据：12 步全 ok，体积 = 10000 mm³（1e-05 m³）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_document_info", {}),
        ("sw_list_features", {}),
        ("sw_list_bodies", {}),
        ("sw_get_mass_properties", {}),
        ("sw_set_view_orientation", {"view_name": "isometric"}),
        ("sw_zoom_to_fit", {}),
        ("sw_rebuild_model", {}),
    ]
    done = []
    volume = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_mass_properties":
            volume = (payload.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 1e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 1e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积不符：%r（期望 1e-05 m³ = 10000 mm³）" % volume],
            "checks": checks}


def _sw_export_flow(client, context):
    """SW 剧本四：建块 → 存盘 → 导出 STEP / STL，并**验文件真写了**。

    判据：8 步全 ok；STEP 首行是 ISO-10303-21；STL > 100 B；目录里三个文件都在。
    临时目录随 cleanup 删掉，不留垃圾。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_export_")
    part = os.path.join(work, "probe_part.SLDPRT")
    step = os.path.join(work, "probe_part.step")
    stl = os.path.join(work, "probe_part.stl")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_export_step", {"path": step}),
        ("sw_export_stl", {"path": stl}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    sizes = {os.path.basename(f): (os.path.getsize(f) if os.path.exists(f) else 0)
             for f in (part, step, stl)}
    head = ""
    if os.path.exists(step):
        with open(step, "rb") as fh:
            head = fh.read(32).decode("latin-1", "replace").strip()
    ok_step = head.startswith("ISO-10303-21")
    ok_stl = sizes.get("probe_part.stl", 0) > 100
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "step_header", "got": head[:24], "want": "ISO-10303-21", "ok": ok_step},
        {"check": "stl_bytes", "got": sizes.get("probe_part.stl"), "want": ">100", "ok": ok_stl},
    ]
    problems = []
    if not ok_step:
        problems.append("STEP 头不对：%r" % head[:32])
    if not ok_stl:
        problems.append("STL 太小或没写：%s B" % sizes.get("probe_part.stl"))
    return {"ok": ok_step and ok_stl,
            "reads": {"steps": done, "files": sizes, "step_header": head[:32], "workdir": work},
            "errors": problems, "checks": checks}


def _sw_props_flow(client, context):
    """SW 剧本五：建块 → 倒角 → 抽壳 → 自定义属性 → 配置 → 材料 → 重建诊断（14 步）。

    判据：14 步全 ok；自定义属性"料号"读回 A-001；激活配置是 CFG_TEST。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_chamfer", {"distance": 2}),
        ("sw_shell", {"thickness": 2, "face_index": -1}),
        ("sw_set_custom_property", {"name": "料号", "value": "A-001"}),
        ("sw_get_custom_properties", {}),
        ("sw_add_configuration", {"name": "CFG_TEST"}),
        ("sw_list_configurations", {}),
        ("sw_set_material", {"name": "AISI 304"}),
        ("sw_get_material", {}),
        ("sw_rebuild_diagnostics", {"full": True}),
    ]
    done = []
    properties: dict = {}
    active = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        reads = payload.get("reads") or {}
        if name == "sw_get_custom_properties":
            properties = reads.get("properties") or {}
        if name == "sw_list_configurations":
            active = reads.get("active")
    stored = str(properties.get("料号", ""))
    ok_prop = "A-001" in stored
    ok_cfg = active == "CFG_TEST"
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "custom_property", "got": stored, "want": "A-001", "ok": ok_prop},
        {"check": "active_configuration", "got": active, "want": "CFG_TEST", "ok": ok_cfg},
    ]
    problems = []
    if not ok_prop:
        problems.append("自定义属性没读到：%r" % stored)
    if not ok_cfg:
        problems.append("激活配置不是 CFG_TEST：%r" % active)
    return {"ok": ok_prop and ok_cfg,
            "reads": {"steps": done, "properties": properties, "active_configuration": active},
            "errors": problems, "checks": checks}


def _nx_batch(client, tools):
    """NX 批量冒烟：每条能力都**独立开一次 run_journal 会话**（实测 13 s/条）。

    和 SW 不同，NX 的能力之间不共享文档——`nx_measure_mass` 那条会自己建块再量，
    所以这里只要求"每条都跑通、判据都过"，不做跨步断言。
    """
    done = []
    failures = []
    for name in tools:
        try:
            payload = client.call(name, {})
        except Exception as exc:                       # noqa: BLE001
            failures.append("%s 抛异常：%s: %s" % (name, type(exc).__name__, str(exc)[:120]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(payload.get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(payload.get("errors"))[:160]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "batch_ok", "got": len(done) - len(failures),
                        "want": len(tools), "ok": not failures}]}


def _sw_equations_flow(client, context):
    """SW 剧本六：方程 / 全局变量 / 镜向 / 回滚 / 抑制-解除 / 显示模式（12 步）。

    判据：12 步全 ok；方程表里 W=40 与 H=10 都在（count=2）。
    注：`sw_pattern_feature` 需要先选中特征，实测直接调会 backend error → 本剧本不含它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_add_equation", {"expression": '"W" = 40'}),
        ("sw_get_equations", {}),
        ("sw_set_global_variable", {"name": "H", "value": 10}),
        ("sw_list_global_variables", {}),
        ("sw_mirror_feature", {"plane": "前视基准面"}),
        ("sw_feature_rollback", {"location": "end"}),
        ("sw_set_display_mode", {"mode": "shaded"}),
    ]
    done = []
    equations: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_list_global_variables":
            equations = (payload.get("reads") or {}).get("equations") or []
    # 用**原始方程文本**比，别比 json.dumps（会多出 \" 转义，把自己坑了）
    text = " | ".join(str(item.get("equation", "")) for item in equations
                      if isinstance(item, dict))
    ok_w = '"W" = 40' in text
    ok_h = '"H" = 10' in text
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "equation_count", "got": len(equations), "want": 2, "ok": len(equations) >= 2},
        {"check": "equations_present", "got": text[:120], "want": "W=40 与 H=10", "ok": ok_w and ok_h},
    ]
    problems = []
    if not ok_w:
        problems.append("方程 W=40 没读到：%s" % text[:120])
    if not ok_h:
        problems.append("全局变量 H=10 没读到：%s" % text[:120])
    return {"ok": ok_w and ok_h, "reads": {"steps": done, "equations": equations},
            "errors": problems, "checks": checks}


def _sw_sketch_flow(client, context):
    """SW 剧本七：草图类 10 个工具（弧/多边形/椭圆/中心线/偏移/线性阵列…）。

    先建块（体积可校验），再开第二张草图把草图工具跑一遍；草图不改体积，
    所以末了仍判 10000 mm³——用体积确认"没把实体搞坏"。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_arc", {"cx": 10.0, "cy": 10.0, "radius": 5.0,
                           "start_angle_deg": 0, "end_angle_deg": 180}),
        ("sw_sketch_polygon", {"cx": 20.0, "cy": 20.0, "num_sides": 6,
                               "circumscribed_radius": 5.0}),
        ("sw_sketch_ellipse", {"cx": 30.0, "cy": 10.0, "semi_major": 5.0,
                               "semi_minor": 3.0}),
        ("sw_sketch_centerline", {"x1": 0.0, "y1": -5.0, "x2": 0.0, "y2": 30.0}),
        ("sw_sketch_offset", {"offset_mm": 2.0}),
        ("sw_sketch_linear_pattern", {"x_count": 2, "y_count": 1,
                                       "x_spacing_mm": 20.0, "y_spacing_mm": 0.0}),
        ("sw_exit_sketch", {}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    volume = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_mass_properties":
            volume = (payload.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 1e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 1e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积被改坏了：%r（期望 1e-05）" % volume],
            "checks": checks}


def _sw_drawing_flow(client, context):
    """SW 剧本八：零件 → 存盘 → 出图（主视图）→ 尺寸标注 → 导出 PDF。

    判据：8 步全 ok；PDF 首字节是 %PDF 且 > 1000 B。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwg_")
    part = os.path.join(work, "dwg_part.SLDPRT")
    pdf = os.path.join(work, "dwg_out.pdf")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part}),
        ("sw_add_drawing_dimension", {}),
        ("sw_export_drawing_pdf", {"path": pdf}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    size = os.path.getsize(pdf) if os.path.exists(pdf) else 0
    head = b""
    if size:
        with open(pdf, "rb") as fh:
            head = fh.read(4)
    ok_pdf = head == b"%PDF" and size > 1000
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pdf_header", "got": head.decode("latin-1"), "want": "%PDF", "ok": head == b"%PDF"},
        {"check": "pdf_bytes", "got": size, "want": ">1000", "ok": size > 1000},
    ]
    return {"ok": ok_pdf, "reads": {"steps": done, "pdf_bytes": size, "workdir": work},
            "errors": [] if ok_pdf else ["PDF 不对：head=%r size=%d" % (head, size)],
            "checks": checks}


def _sw_light_reads(client, context):
    """SW 只读"轻"工具批量（不建不改不关文档，因此在夹具打开时也安全）。

    实测：夹具（450 隔音罩，几百特征）打开时这 12 个都 0–11 s 返回；
    真正会卡死的是"同会话里建/关文档"的那类操作（见 docs/coverage-plan.md）。
    """
    import threading
    tools = ["sw_get_status", "sw_operation_status", "sw_proxy_tools",
             "sw_list_open_documents", "sw_list_materials", "sw_docs_stats",
             "sw_docs_query", "sw_registry", "sw_inspect_active",
             "sw_list_documents_dirty", "sw_get_model_info", "sw_bounding_box"]
    done, failures = [], []
    for name in tools:
        box: dict = {}

        def _one(tool_name=name):
            try:
                box["payload"] = client.call(tool_name, {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:110])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(60)
        if worker.is_alive():
            failures.append("%s 超时（>60 s）" % name)
            done.append({"tool": name, "ok": False})
            continue
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:120]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "light_reads_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


def _sw_surface_flow(client, context):
    """SW 剧本九：曲面族（平面区域→加厚→拉伸曲面→偏移曲面）11 步。

    判据：11 步全 ok，且实体/曲面体都存在（sw_list_bodies 里两类计数都 >0）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_planar_surface", {}),
        ("sw_thicken_surface", {"thickness": 0.002}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_circle", {"cx": 10.0, "cy": 10.0, "radius": 5.0}),
        ("sw_exit_sketch", {}),
        ("sw_extruded_surface", {"depth": 20}),
        ("sw_offset_surface", {"distance": 0.002}),
        ("sw_list_bodies", {}),
    ]
    done = []
    body_counts: dict = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_list_bodies":
            body_counts = payload.get("reads") or {}
    solid = int(body_counts.get("solid_bodies") or body_counts.get("solids") or 0)
    surface = int(body_counts.get("surface_bodies") or body_counts.get("surfaces") or 0)
    ok_bodies = solid >= 1 and surface >= 1
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "body_kinds", "got": {"solid": solid, "surface": surface},
         "want": "两者都 >0", "ok": ok_bodies},
    ]
    return {"ok": ok_bodies, "reads": {"steps": done, "bodies": body_counts},
            "errors": [] if ok_bodies else ["实体/曲面计数异常：%r" % (body_counts,)],
            "checks": checks}


def _sw_sheet_flow(client, context):
    """SW 剧本十：钣金基体法兰 → 展开图信息（6 步）。

    判据：6 步全 ok，且 get_flat_pattern_info 认到 FlatPattern（或至少报出厚度）。
    注：`sw_hem` 实测 backend error（需要先选边），本剧本不含它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 60.0}),
        ("sw_exit_sketch", {}),
        ("sw_base_flange", {"thickness_mm": 2, "radius_mm": 2, "depth_mm": 30}),
        ("sw_get_flat_pattern_info", {}),
    ]
    done = []
    flat: dict = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_flat_pattern_info":
            flat = payload.get("reads") or {}
    # 实际键是 flat_pattern_feature（例如 '平展型式6'），别再猜别的名字
    has_flat = bool(flat.get("flat_pattern_feature") or flat.get("flat_pattern")
                    or flat.get("has_flat_pattern") or flat.get("feature")
                    or flat.get("thickness_mm"))
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "flat_pattern", "got": flat, "want": "认到展开图或厚度", "ok": has_flat},
    ]
    return {"ok": has_flat, "reads": {"steps": done, "flat_pattern": flat},
            "errors": [] if has_flat else ["展开图信息为空：%r" % (flat,)],
            "checks": checks}


def _sw_drawing2_flow(client, context):
    """SW 剧本十一：零件→IGES→出图→注释→旋转视图→导出 PDF/DWG（12 步）。

    判据：12 步全 ok；IGES > 1 KB；PDF 头 %PDF；DWG 头 AC10xx（AutoCAD 版本标记）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwg2_")
    part = os.path.join(work, "p.SLDPRT")
    pdf = os.path.join(work, "p.pdf")
    dwg = os.path.join(work, "p.dwg")
    iges = os.path.join(work, "p.iges")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_export_iges", {"path": iges}),
        ("sw_new_drawing", {"model": part}),
        ("sw_note", {"text": "验收注释", "x": 0.1, "y": 0.1}),
        ("sw_view_rotate", {"angle_deg": 15}),
        ("sw_export_drawing_pdf", {"path": pdf}),
        ("sw_export_drawing_dwg", {"path": dwg}),
    ]
    done = []
    iges_actual = iges
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        # sw_export_iges 会把 .iges 归一成 .igs，实际路径在 reads.path 里
        if name == "sw_export_iges":
            iges_actual = (payload.get("reads") or {}).get("path") or iges

    def head(path, n=8):
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as fh:
            return fh.read(n)

    sizes = {os.path.basename(f): (os.path.getsize(f) if os.path.exists(f) else 0)
             for f in (iges_actual, pdf, dwg)}
    iges_key = os.path.basename(iges_actual)
    ok_iges = sizes.get(iges_key, 0) > 1000
    ok_pdf = head(pdf, 4) == b"%PDF"
    ok_dwg = head(dwg, 4).startswith(b"AC10")
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "iges_bytes", "got": sizes.get(iges_key), "want": ">1000", "ok": ok_iges},
        {"check": "pdf_header", "got": head(pdf, 4).decode("latin-1"), "want": "%PDF", "ok": ok_pdf},
        {"check": "dwg_header", "got": head(dwg, 6).decode("latin-1"), "want": "AC10xx", "ok": ok_dwg},
    ]
    problems = []
    if not ok_iges:
        problems.append("IGES 太小/没写：%r" % (sizes,))
    if not ok_pdf:
        problems.append("PDF 头不对：%r" % head(pdf, 4))
    if not ok_dwg:
        problems.append("DWG 头不对：%r" % head(dwg, 6))
    return {"ok": ok_iges and ok_pdf and ok_dwg,
            "reads": {"steps": done, "files": sizes, "workdir": work},
            "errors": problems, "checks": checks}


def _flow(client, steps):
    """顺序调用若干工具；任一步失败就带着证据停，全过则合成一个 payload。

    一条用例覆盖 3–6 个工具，失败点明确（不会只看到最后一步的错）。
    """
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                      # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _eplan_missing(context: dict) -> bool:
    """没有 EPLAN **平台本体** 时跳过真机读取类用例。

    注意：光看 EPLAN 目录会误判——本机只装了 EPLAN License Client
    （Common\\EClientService.exe），没有 Platform，Eplan.exe 不存在。
    所以这里查注册表里的平台条目。
    """
    import winreg
    keys = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
    for path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, name) as item:
                            display = winreg.QueryValueEx(item, "DisplayName")[0]
                    except OSError:
                        continue
                    if "EPLAN" not in str(display):
                        continue
                    lowered = str(display).lower()
                    if "license" in lowered or "identity" in lowered:
                        continue
                    return False
        except OSError:
            continue
    return not any(os.path.isfile(p) for p in
                   (r"C:\Program Files\EPLAN\Platform\2.9.4\Bin\Eplan.exe",
                    r"C:\Program Files\EPLAN\Electric P8\2.9.4\Bin\Eplan.exe"))


_EPLAN_INTENT_MODEL = {
    "schema_version": "eplan-design-intent-1",
    "devices": [
        {"tag": "PS1", "kind": "psu", "part_number": None,
         "ports": [{"id": "24V", "conductor": "DC24", "required": True, "physical_pin": None},
                   {"id": "0V", "conductor": "DC0", "required": True, "physical_pin": None}]},
        {"tag": "PLC1", "kind": "plc", "part_number": None,
         "ports": [{"id": "L+", "conductor": "DC24", "required": True, "physical_pin": None},
                   {"id": "M", "conductor": "DC0", "required": True, "physical_pin": None},
                   {"id": "Q0.0", "conductor": "SIGNAL", "required": True,
                    "physical_pin": None, "plc_address": "Q0.0"},
                   {"id": "Q0.1", "conductor": "SIGNAL", "required": True,
                    "physical_pin": None, "plc_address": "Q0.1"}],
         "io_groups": [{"id": "DO", "channels": ["Q0.0", "Q0.1"], "common_port": "M",
                        "supply_port": "L+", "common_conductor": "DC0", "type": "PNP"}]},
        {"tag": "KA1", "kind": "relay", "part_number": None,
         "ports": [{"id": "A1", "conductor": "SIGNAL", "required": True, "physical_pin": None},
                   {"id": "A2", "conductor": "DC0", "required": True, "physical_pin": None}]},
        {"tag": "KA2", "kind": "relay", "part_number": None,
         "ports": [{"id": "A1", "conductor": "SIGNAL", "required": True, "physical_pin": None},
                   {"id": "A2", "conductor": "DC0", "required": True, "physical_pin": None}]},
    ],
    "connections": [
        {"id": "W1", "from": "PS1:24V", "to": "PLC1:L+"},
        {"id": "W2", "from": "PS1:0V", "to": "PLC1:M"},
        {"id": "W3", "from": "PLC1:Q0.0", "to": "KA1:A1"},
        {"id": "W4", "from": "PLC1:Q0.1", "to": "KA2:A1"},
        {"id": "W5", "from": "PS1:0V", "to": "KA1:A2"},
        {"id": "W6", "from": "PS1:0V", "to": "KA2:A2"},
    ],
    "forbidden_pairs": [["PLC1:Q0.0", "PLC1:Q0.1"], ["PS1:24V", "PS1:0V"]],
    "forward_reverse": {"forward_output": "PLC1:Q0.0", "reverse_output": "PLC1:Q0.1",
                        "mutual_exclusion": True,
                        "restart_requires_new_start_edge": True,
                        "reversal_requires_standstill": True},
}


EPLAN_CASES = [
    {"id": "eplan.capabilities", "tool": "eplan_capabilities",
     "title": "EPLAN 能力自报（画像 / 版本约束 / 支持与不支持）",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.profile": "review",
                      "reads.server": "eplan29-lab"},
     "timeout_s": 180},

    {"id": "eplan.tool_catalog", "tool": "eplan_tool_catalog",
     "title": "工具目录（review 画像应给出 15 条）",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.profile": "review", "reads.count": 15},
     "timeout_s": 180},

    {"id": "eplan.bridge.discover", "tool": "eplan_bridge_discover",
     "title": "原生 bridge 发现（EPLAN 没开时应是空列表而不是报错）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 180},

    {"id": "eplan.runtime.no_snapshot", "tool": "eplan_runtime_status",
     "title": "没有快照时 runtime_status 明确返回 ok=false（不假装读过原生）",
     "args": {}, "expect_ok": False,
     "expect_reads": {"reads.snapshot.available": False,
                      "reads.snapshot.live_verified_this_call": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.snapshot.reject_empty", "tool": "eplan_native_snapshot_validate",
     "title": "空快照必须被拒：scope=provided_full_snapshot_offline、construction_ready=false",
     "args": {"capture": {}, "plan": {}},
     "expect_ok": False,
     "expect_reads": {"reads.scope": "provided_full_snapshot_offline",
                      "reads.native_read_this_call": False,
                      "reads.construction_ready": False,
                      "reads.commissioning_ready": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.help.not_built", "tool": "eplan_help_search",
     "title": "没建索引时 help_search 明确拒绝（HELP_INDEX_NOT_BUILT），不假装查过",
     "args": {"query": "Generate"},
     "expect_ok": False,
     "expect_reads": {"reads.error": "HELP_INDEX_NOT_BUILT"},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.intent.validate", "tool": "eplan_design_intent_validate",
     "title": "离线设计意图校验：6 根线分成 4 组、给出 14 条告警",
     "args": {"model": _EPLAN_INTENT_MODEL},
     "expect_ok": True,
     "expect_reads": {"reads.wire_groups": 4,
                      "reads.scope": "offline_declared_wire_graph_and_constraints_only"},
     "timeout_s": 180},
]


# ── catia（CATIA V5：建模 / 曲面 / 原生 Analysis）────────────────────────
def _catia_missing(context: dict) -> bool:
    """本机没装 CATIA 就跳过（2026-11-04 实测未安装）。"""
    import os
    roots = [r"C:\Program Files\Dassault Systemes", r"D:\Program Files\Dassault Systemes",
             r"C:\Program Files (x86)\Dassault Systemes"]
    return not any(os.path.isdir(r) for r in roots)


CATIA_CASES = [
    {"id": "catia.operation.status", "tool": "catia_operation_status",
     "title": "COM worker 状态（不进队列，不启动 CATIA）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    {"id": "catia.health", "tool": "catia_health_check",
     "title": "CATIA 可用性自检",
     "args": {},
     "expect_ok": True,
     "timeout_s": 120,
     "skip_if": _catia_missing},
]


KITS = {
    "sw": {"module": "nsa_mcp_hub.servers.sw_mcp", "setup": sw_setup,
           "teardown": sw_teardown, "cases": SW_CASES},
    "nx": {"module": "nsa_mcp_hub.servers.nx_mcp", "setup": nx_setup,
           "cases": NX_CASES},
    "acad": {"module": "nsa_mcp_hub.servers.acad_mcp", "setup": acad_setup, "between": acad_between, "teardown": acad_teardown, "cases": ACAD_CASES},
    "gx": {"module": "nsa_mcp_hub.servers.gx_mcp", "cases": GX_CASES},
    "codesys": {"module": "nsa_mcp_hub.servers.codesys_mcp", "setup": codesys_setup,
                "cases": CODESYS_CASES},
    "ug": {"module": "nsa_mcp_hub.servers.ug_mcp", "cases": UG_CASES},
    "catia": {"module": "nsa_mcp_hub.servers.catia_mcp", "cases": CATIA_CASES},
    "eplan": {"module": "nsa_mcp_hub.servers.eplan_mcp", "cases": EPLAN_CASES},
    "autoshop": {"module": "nsa_mcp_hub.servers.autoshop_mcp", "setup": autoshop_setup, "between": autoshop_between, "teardown": autoshop_teardown, "cases": AUTOSHOP_CASES},
}
