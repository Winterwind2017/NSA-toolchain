"""swkit.registry —— 工具状态登记表（本项目的核心资产）

这份表的用途不是"列出有多少工具"，而是**把"哪些真的能用、依据是什么、哪些根本用不了"
写死成代码**，这样 MCP 层、CLI、agent skill 都从同一个来源说话，不会各说各话。

状态口径：

* `verified`   —— 本机 SW 2025 SP4.1 实测通过，有可复现的判据（组件数/特征数/符号数/标志位）。
* `unstable`   —— 曾成功但会挂起或崩溃，不进自动回归。
* `broken`     —— 有明确依据证伪（类型库无该方法 / 参数横扫全失败 / 官方标注废弃且替代不可用）。
* `unverified` —— 上游提供但本项目尚未复核，**不建议用于交付**。

依据来源：`docs/UNSUPPORTED.md`、`docs/RECIPES.md`、以及本仓库对应实现里的证据字典。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = ["ToolEntry", "REGISTRY", "get", "by_status", "summary"]


@dataclass(frozen=True)
class ToolEntry:
    name: str
    group: str
    status: str
    api: str
    evidence: str = ""
    note: str = ""
    implemented: bool = False      # 本仓库里是否已编码、可经 CLI/MCP 直接调用


def _e(name: str, group: str, api: str, evidence: str, note: str = "",
       implemented: bool = False) -> Tuple[str, ToolEntry]:
    return name, ToolEntry(name, group, "verified", api, evidence, note, implemented)


_VERIFIED: List[Tuple[str, ToolEntry]] = [
    # ── 零件 / 草图 / 特征（round 1–39 实测）─────────────────────
    _e("sw_get_bounding_box", "meta", "IBody2.GetBodyBox",
       "X[-50,50] Y[-30,30] Z[0,10] mm"),
    _e("sw_list_materials", "meta", "解析 .sldmat", "3 库 / 29 分类 / 474 材料"),
    _e("sw_shell", "feature", "InsertFeatureShell + IFace2.Select2", "面 7→14"),
    _e("sw_thicken_surface", "feature", "FeatureBossThicken", "加厚特征=1，面 7→14"),
    _e("sw_offset_surface", "feature", "InsertOffsetSurface", "曲面 1→2"),
    _e("sw_split_line", "feature", "InsertSplitLineProject(True,False)",
       "特征 22→23（返回 0 但成功）"),
    _e("sw_linear_pattern", "feature", "FeatureLinearPattern3，方向 mark=1", "特征 22→23"),
    _e("sw_circular_pattern", "feature", "FeatureCircularPattern3，轴 mark=1", "特征 22→23"),
    _e("sw_sketch_construction", "sketch", "ISketchSegment.ConstructionGeometry",
       "True→False 往返"),
    _e("sw_sketch_text", "sketch", "InsertSketchText", "草图线段 0→1"),
    _e("sw_add_sketch_constraint", "sketch", "SketchAddConstraints", "约束 0→1"),
    # ── 出图 ──────────────────────────────────────────────────
    _e("sw_add_centerline", "drawing", "InsertCenterLine", "中心线 0→6"),
    _e("sw_add_center_mark", "drawing", "AddCenterMark，圆边 mark=1", "中心标记 0→6"),
    _e("sw_add_datum_feature", "drawing", "InsertDatumTag2（零参）", "计数 0→1"),
    _e("sw_add_gtol", "drawing", "InsertGtol（零参）", "计数 0→1"),
    _e("sw_add_weld_symbol", "drawing", "InsertWeldSymbol3（零参）", "计数 0→1"),

    _e("sw_add_drawing_dimension", "drawing", "AddDimension2，两边 mark=1", "尺寸 0→1"),
    _e("sw_add_hole_table", "drawing", "InsertHoleTable2 + 选中圆边 + 激活视图",
       "孔表 0→1"),
    _e("sw_add_auxiliary_view", "drawing", "CreateAuxiliaryView（零参）", "视图 2→3"),
    _e("sw_add_broken_view", "drawing", "IView.InsertBreak2", "断线 0→1"),
    _e("sw_create_section_view", "drawing",
       "CreateSectionViewData + CreateSectionView", "返回 True"),
    _e("sw_note", "drawing", "InsertNote", "文本 + 位置 (0.05,0.05) 读回"),
    _e("sw_add_annotation", "drawing", "InsertNote（图纸）", "注释 0→1"),
    _e("sw_take_photoview_screenshot", "drawing", "SaveBMP（替代实现）",
       "1200×800 / 24bit / 2.88 MB"),
    _e("sw_activate_display_state", "meta", "ApplyDisplayState(name)", "返回 True"),
    # ── 装配（round 40 全部打通，9/9）────────────────────────────
    _e("sw_check_interference", "assembly", "IToolsCheckInterference2",
       "A/B：重叠 1 处 vs 分开 0 处"),
    _e("sw_fix_component", "assembly", "IComponent2.IsFixed=True", "IsFixed 读回 True"),
    _e("sw_explode_assembly", "assembly", "IViewManager.CreateExplodedView", "爆炸视图数 1"),
    _e("sw_show_all_components", "assembly", "IAssemblyDoc.ShowComponent", "可调"),
    _e("sw_move_component", "assembly", "变换拷贝法（借临时件的 Transform2）",
       "ΔX=0.030000"),
    _e("sw_add_balloon", "drawing", "IAutoBalloon2 + INote.GetText",
       "读回 '1'（BOM 项号）"),
    _e("sw_mirror_component", "assembly",
       "CreateDefinition(116) + IMirrorComponentFeatureData + CreateFeature",
       "特征『镜向零部件1』、组件 2→4、IsMirrored×2；负面对照可复现旧法 no-op",
       "MirrorComponents3 在 SW2025 已废弃"),
    _e("sw_pattern_component_linear", "assembly", "FeatureLinearPattern5",
       "组件 2→4/2→5、特征 +3/+4、IsPatternInstance×2/×3",
       "组件 mark=1、方向 mark=2（与特征相反）"),
    _e("sw_pattern_component_circular", "assembly", "FeatureCircularPattern5",
       "组件 2→4（120°）、IsPatternInstance×2",
       "组件 mark=1、方向 mark=2"),
]

_UNSTABLE: List[Tuple[str, ToolEntry]] = [
    ("sw_add_sketch_dimension",
     ToolEntry("sw_add_sketch_dimension", "sketch", "unstable",
               "AddAlongXDimension mark=1",
               "round 17 成功 0.01→0.03；round 32 挂起并崩溃过一次",
               "不进自动回归；调用方需自行超时保护")),
    ("sw_show_all_planes",
     ToolEntry("sw_show_all_planes", "meta", "unstable", "UnblankRefGeom",
               "API 存在且可调，但 IFeature.Visible 不反映图形可见性，无法构造 A/B",
               "判据未立，不宜宣称已修")),
]

_BROKEN: List[Tuple[str, ToolEntry]] = [
    ("sw_delete_face",
     ToolEntry("sw_delete_face", "feature", "broken", "IBody2.DeleteFaces3",
               "option=0/1/2/4/8 × flag=T/F 共 10 组全 (False,False)，面数不变",
               "换 VARIANT(VT_ARRAY|VT_DISPATCH) 传数组同样无效")),
    ("sw_knit_surfaces",
     ToolEntry("sw_knit_surfaces", "feature", "broken", "（无）",
               "sldworks.tlb 无 InsertKnitSurface",
               "只有 IMirrorSolidFeatureData.KnitSurface / IPartingSurfaceFeatureData.Knit 这类别的特征的属性")),
    ("sw_start_macro_recording",
     ToolEntry("sw_start_macro_recording", "meta", "broken", "（无）",
               "类型库穷举无 StartRecording",
               "含 record/macro 的只有 InsertMacroFeature*/IJournalManager.WriteJournalToMacro")),
    ("sw_stop_macro_recording",
     ToolEntry("sw_stop_macro_recording", "meta", "broken", "（无）",
               "类型库穷举无 StopRecording",
               "同上")),
]

_STUDY_META: List[Tuple[str, ToolEntry]] = [
    # ── Simulation（2026-10-19 实测；40×40 角码 / AISI 304）───────────
    _e("sw_sim_status", "study", "sw_sim.status",
       "文档/材质/加载项/研究列表可读"),
    _e("sw_sim_faces", "study", "sw_sim.faces", "列出 52 个面（索引+中心+尺寸）"),
    _e("sw_sim_setup", "study", "sw_sim.setup", "约束面=0 成功（1→码2, 2→4, 3/4/5→7）",
       "安全网格 size=0.02 / tol=0.002 / type=1，更低会吃满 16 GB"),
    _e("sw_sim_mesh", "study", "sw_sim.mesh", "网格生成成功（安全档）"),
    _e("sw_sim_run", "study", "sw_sim.run", "40 mm 级零件 11–13 分钟，star.exe 峰值 ~15 GB"),
    _e("sw_sim_read", "study", "sw_sim.read",
       "位移 max 0.698424 mm @100 N；1 N→0.006984 mm（恰好 1/100，线性自洽）",
       "应力读数会话相关：求解后同会话 1.497e9，重开文档恒 code 1；固定端锐边是应力奇异（伪值）"),
    _e("sw_sim_solve", "study", "sw_sim.solve", "一条龙 13–15 分钟，结果与手工一致"),
    _e("sw_sim_addin_check", "study", "sw_adv.sim", "加载项对象存在但无可用成员（本机实测定论）"),
    # ── Motion（2026-10-19 实测：循环线打包 8 号机）──────────────────
    _e("sw_motion_list", "study", "sw_motion.list",
       "算例/要素/时长可读（装配体2 → 运动算例 1）"),
    _e("sw_motion_read", "study", "sw_motion.read",
       "速度 0.1 m/s、IsOutOfDate=False",
       "结果集索引必须=4；1/2 是空壳；位移不能用 GetCMPosition；组件须 comtypes IComponent2"),
    # ── 元数据 / 只读审计 ────────────────────────────────────────
    _e("sw_props", "meta", "sw_adv.props", "单文件自定义属性+配置（含中文属性名）"),
    _e("sw_scan", "meta", "sw_adv.scan", "一会话扫目录，275 文件一轮完成"),
    _e("swdm_stats", "meta", "swdm_lite.stats",
       "275 文件(168 prt / 79 drw / 28 asm)、属性 136、组件行 2684、视图行 351、表格 5"),
    _e("swdm_query", "meta", "swdm_lite.query", "按 属性/目录/扩展名 过滤命中",
       "没有全文检索（只有 --prop/--dir/--ext）"),
    _e("swdm_bom", "meta", "swdm_lite.bom", "装配组件行 2684（来自 28 个装配）"),
    _e("swdm_tables", "meta", "swdm_lite.tables", "工程图表格 5 张，视图行 351"),
    _e("sw_ovba_selftest", "meta", "sw_ovba.selftest",
       "enable.swp：dir 737B→1106B、PROJECTCODEPAGE=1252、2 模块、304B 源码"),
    _e("sw_ovba_dump", "meta", "sw_ovba.dump", "解出模块源码（Attribute VB_Name 等）"),
]

_UNVERIFIED: List[Tuple[str, ToolEntry]] = [
    ("sw_add_surface_finish",
     ToolEntry("sw_add_surface_finish", "drawing", "unverified",
               "InsertSurfaceFinishSymbol2(14 参)",
               "插入只返回 True；TLB 里 IDrawingDoc 只有 Insert/Modify，IView 无任何粗糙度 getter",
               "已从 verified 降级：拿不到计数就无法证明符号真的生成（2026-10-20 复核）")),
    ("sw_dxp",
     ToolEntry("sw_dxp", "meta", "unverified", "sw_adv.dxp",
               "方案名与标注数量可读（DimXpert）",
               "autodim=True 会运行自动尺寸并保存文件——破坏性，默认关闭")),
    ("sw_flow_check",
     ToolEntry("sw_flow_check", "meta", "unverified", "sw_adv.flow",
               "加载项自检与建工程可调",
               "未跑通求解，不能算打通")),
]

# 注意：上表刻意保留重复键时的"后写覆盖"语义，避免手抖写重时静默丢条目。
REGISTRY: Dict[str, ToolEntry] = {}
for _name, _entry in _VERIFIED + _STUDY_META + _UNSTABLE + _UNVERIFIED + _BROKEN:
    REGISTRY[_name] = _entry


# ── 本仓库已编码、可经 CLI/MCP 直接调用的条目（单一事实来源）───────────────
_IMPLEMENTED = {
    # 装配（verified/*）
    "sw_pattern_component_linear", "sw_pattern_component_circular", "sw_mirror_component",
    # 仿真 / 运动（study/*）
    "sw_sim_status", "sw_sim_faces", "sw_sim_setup", "sw_sim_mesh", "sw_sim_run",
    "sw_sim_read", "sw_sim_solve", "sw_sim_addin_check",
    "sw_motion_list", "sw_motion_read",
    # 零件 / 特征（verified/part.py，2026-10-20 真机 8/8）
    "sw_get_bounding_box", "sw_take_photoview_screenshot", "sw_shell",
    "sw_linear_pattern", "sw_circular_pattern", "sw_split_line",
    "sw_thicken_surface", "sw_offset_surface",
    # 出图（verified/drawing.py，2026-10-20 真机 7/8；surface_finish 判据不可得，见下）
    "sw_add_center_mark", "sw_add_centerline", "sw_add_datum_feature", "sw_add_gtol",
    "sw_add_weld_symbol", "sw_note", "sw_add_annotation",
    # 装配其余（verified/asm_ops.py，2026-10-20 真机 4/4，含干涉 A/B）
    "sw_check_interference", "sw_fix_component", "sw_show_all_components",
    "sw_explode_assembly", "sw_move_component",
    # 草图 / 文档级（verified/sketch.py、verified/model.py，2026-10-20 真机 5/5）
    "sw_sketch_construction", "sw_sketch_text", "sw_add_sketch_constraint",
    "sw_activate_display_state", "sw_list_materials",
    # 元数据（meta/*）
    "sw_props", "sw_scan", "swdm_stats", "swdm_query", "swdm_bom", "swdm_tables",
    "sw_ovba_selftest", "sw_ovba_dump",
}

import dataclasses as _dc
for _n in _IMPLEMENTED:
    _entry = REGISTRY.get(_n)
    if _entry is not None and not _entry.implemented:
        REGISTRY[_n] = _dc.replace(_entry, implemented=True)

# 另有 3 个元信息工具不在表内（sw_status / sw_registry / sw_document_info），
# 由 MCP/CLI 直接提供，不需要判据。
META_TOOLS = ("sw_status", "sw_registry", "sw_document_info")


def get(name: str) -> ToolEntry:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError("未登记的工具：%s（先在 registry.py 里补一条，附依据）" % name)


def by_status(status: str) -> List[ToolEntry]:
    return [e for e in REGISTRY.values() if e.status == status]


def summary() -> Dict[str, int]:
    """按状态计数，并单列"已验证但本仓库尚未编码"的数量。

    这样清单不会虚高：`verified` 是"配方已验证"，`implemented` 才是"现在就能调"。
    """
    out: Dict[str, int] = {}
    for entry in REGISTRY.values():
        out[entry.status] = out.get(entry.status, 0) + 1
    out["implemented"] = sum(1 for e in REGISTRY.values() if e.implemented)
    out["verified_not_implemented"] = sum(
        1 for e in REGISTRY.values() if e.status == "verified" and not e.implemented)
    out["meta_tools"] = len(META_TOOLS)
    return out
