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


def _e(name: str, group: str, api: str, evidence: str, note: str = "") -> Tuple[str, ToolEntry]:
    return name, ToolEntry(name, group, "verified", api, evidence, note)


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
    _e("sw_add_surface_finish", "drawing", "InsertSurfaceFinishSymbol2", "计数 0→1"),
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
       "特征『镜像零部件1』、组件 2→4、IsMirrored×2；负面对照可复现旧法 no-op",
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

# 注意：上表刻意保留重复键时的"后写覆盖"语义，避免手抖写重时静默丢条目。
REGISTRY: Dict[str, ToolEntry] = {}
for _name, _entry in _VERIFIED + _UNSTABLE + _BROKEN:
    REGISTRY[_name] = _entry


def get(name: str) -> ToolEntry:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError("未登记的工具：%s（先在 registry.py 里补一条，附依据）" % name)


def by_status(status: str) -> List[ToolEntry]:
    return [e for e in REGISTRY.values() if e.status == status]


def summary() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for entry in REGISTRY.values():
        out[entry.status] = out.get(entry.status, 0) + 1
    return out
