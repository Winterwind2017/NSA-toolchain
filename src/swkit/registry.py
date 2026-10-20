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
    _e("sw_flow_check", "meta", "EFDApiSrv.EFDLauncher.Attach2RunningCADInstance + EFDApi.IApplication",
       "附加到运行中 SW：版本 **Flow Simulation 2025 SP3.0 Build 6784**、静默模式 True、工程数 0、CAD 文档对象可取",
       "真正的 API 在 SOLIDWORKS Flow Simulation\\binCFW\\EFDApiSrv.tlb + EFDApi.tlb；FloXpress 的 FloWorks.App 只有 TB_on_* 按钮回调"),
    _e("sw_dxp", "meta", "swdimxpert.tlb: IDimXpertManager/IDimXpertPart",
       "create=False → 无 schema（DimXpertPart=None）；create=True → schema **模式2**、要素 0、标注 0",
       "DimXpert 接口在独立 swdimxpert.tlb（123 接口），不在 sldworks.tlb；入口 Extension.DimXpertManager(config, create)"),
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
    _e("sw_add_surface_finish", "drawing", "InsertSurfaceFinishSymbol2(14 参)",
       "先 ActivateView 再插 → IView.GetSFSymbols 0→1",
       "该 getter 在没有符号时返回 None（不是缺方法）：None 必须当 0，否则会误判为不可验证"),
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
    _e("sw_check_interference", "assembly",
       "IAssemblyDoc.InterferenceDetectionManager.GetInterferenceCount",
       "分开 120mm→**0**；重叠 20mm→**1**；完全重合→**1**（组件按 mm 定位）",
       "老实现走 IToolsCheckInterference2（会弹对话框）；改用管理器，无模态、可回读开关"),
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

# ── 图纸视图/BOM（2026-10-20 真机 2/3）──────────────────────────────
_DRAWING_VIEWS: List[Tuple[str, ToolEntry]] = [
    _e("sw_add_drawing_view", "drawing", "IDrawingDoc.CreateDrawViewFromModelView3",
       "零件图再加 top 视图：视图数 2→3",
       "API 在 IDrawingDoc（不在 Extension）；中文版只认本地化视图名（*上视）"),
    _e("sw_add_bom_table", "drawing", "IView.InsertBomTable2(7 参)",
       "装配图 BOM 建成（BomType=1，返回 CDispatch）",
       "BomType=0 是无效值；需装配图，零件图没有 BOM 项"),
]

# ── 曲面（2026-10-20 真机 2/3）──────────────────────────────────────
_SURFACES: List[Tuple[str, ToolEntry]] = [
    _e("sw_planar_surface", "surface", "IModelDoc.InsertPlanarRefSurface（属性）",
       "闭合矩形草图 → 曲面 0→1",
       "它在本机是**属性**：读取即执行，加括号报 'bool' object is not callable"),
    _e("sw_revolved_surface", "surface", "IModelDoc.InsertRevolvedRefSurface(4 参)",
       "矩形+中心线 → 曲面 0→1；API 在 IModelDoc 上，不在 IModelDoc2"),
    _e("sw_extruded_surface", "surface", "IFeatureManager.FeatureExtruRefSurface3(22 参)",
       "闭合矩形草图 → 曲面 0→1，特征类型 ExtruRefSurface",
       "老接口 IModelDoc.FeatureExtruRefSurface(15 参) 返回 None 不出面；必须先 SelectByID2 选草图 mark 0"),
]

# ── 切除（2026-10-20 真机 3/3，修 P0）────────────────────────────────
_CUTS: List[Tuple[str, ToolEntry]] = [
    _e("sw_fillet", "feature", "FeatureFillet3（高层 14 参版，comtypes）",
       "80×50×12 板 4 条边圆角 5mm：体积 48000→**47382.87**（Δ=-617.13）、面 6→**10**、边 12→**20**",
       "同名两套签名：底层 9 参在 pywin32 下第 7 参 Radii 恒报类型不匹配；高层 14 参（Options 开头）走 comtypes 才通"),
    _e("sw_analyze_draft", "feature",
       "IPartingLineFeatureData.DraftAnalysis + GetFacesByTypeCount",
       "分型线1（夹具 tests/fixtures/draft_parting_line.SLDPRT）：正拔模 **1**、负拔模 **1**、无拔模 **4**、跨面 **0**，合计 6 = 实体面数",
       "顺序关键：AccessSelections 必须在 DraftAnalysis 之前，否则恒 False；GetDefinition 是属性；pywin32 无 QueryInterface 需走 comtypes；分型线本身无法用 API 创建"),
    _e("sw_chamfer", "feature", "IFeatureManager.InsertFeatureChamfer(8 参)",
       "80×50×12 板 4 条边倒角 5mm：体积 48000→**46616.667**（Δ=-1383.33）、面 6→**10**、边 12→**20**",
       "内核把前两参写反（Options/ChamferType）→ 建出空特征；改正后几何真变"),
    _e("sw_cut_extrude", "feature", "IFeatureManager.FeatureCut4(27 参)",
       "80×50×12 板顶面两处 Ø10 通孔：体积 48000→**46115.044**（每孔 −942.478，理论 −942.48）",
       "UseAutoSelect 必须 True（False 时只选草图会静默失败）；Dir=False 才是朝材料里切"),
]

# ── 实体级操作（2026-10-20 真机 2/2）────────────────────────────────
_BODIES: List[Tuple[str, ToolEntry]] = [
    _e("sw_scale_body", "body", "IModelDoc2.InsertScale(5 参)",
       "选中实体后 40×25×20 → **80×50×40**（体积 20000→160000）",
       "不选实体也能调用、不报错，但几何不变 —— 假成功；选实体要用 SOLIDBODY 中心点选"),
    _e("sw_delete_body", "body", "IFeatureManager.InsertDeleteBody",
       "实体数 2→1"),
]

# ── 草图编辑（2026-10-20 真机 4/4）──────────────────────────────────
_SKETCH_EDIT: List[Tuple[str, ToolEntry]] = [
    _e("sw_sketch_offset", "sketch", "ISketchManager.SketchOffset2(6 参)",
       "矩形 4 段/130mm → **8 段/300mm**（偏移 5mm）",
       "真实签名 6 参（TLB 只列 3）：Offset,BothDirections,Chain,CapEnds,MakeConstruction,AddDimensions"),
    _e("sw_sketch_linear_pattern", "sketch", "ISketchManager.CreateLinearSketchStepAndRepeat(12 参)",
       "Ø6 圆 1→**3** 段、总长 18.85→**56.55**（3×20mm 间距）",
       "真实签名 12 参（TLB 只列 6）：第 7 参 DeleteInstances 是字符串，三个 Dim 传 None，须 comtypes"),
    _e("sw_sketch_trim", "sketch", "ISketchManager.SketchTrim(4 参)",
       "矩形+伸出横线：总长 200→190 mm（正好切掉 10 mm 伸出段）"),
    _e("sw_sketch_fillet", "sketch", "ISketchManager.CreateFillet(2 参)",
       "选两条边 → 线段 4→5、总长 130→127.854",
       "真名是 CreateFillet(Radius, ConstrainedCorners)，不是 SketchFillet；必须 comtypes"),
    _e("sw_sketch_chamfer", "sketch", "ISketchManager.CreateChamfer(3 参)",
       "选两条边 → 线段 4→5、总长 130→127.071",
       "第一参是 int 类型（ChamferType），不是距离；角度要弧度"),
    _e("sw_start_3d_sketch", "sketch", "ISketchManager.Insert3DSketch",
       "活动草图存在且 Is3D=True"),
]

# ── 方程/全局变量/参考轴（2026-10-20 真机 4/4）──────────────────
_EQUATIONS: List[Tuple[str, ToolEntry]] = [
    _e("sw_get_equations", "doc", "IEquationMgr.GetCount/Equation/Value",
       "空件 0 条；写入后 1 条可读",
       "IModelDoc2 无 AddEquation；IEquationMgr 必须 comtypes（pywin32 找不到成员）"),
    _e("sw_list_global_variables", "doc", "IEquationMgr.Equation(i)",
       "列出 \"myvar\" = 5.0（值 5.0）",
       "全局变量语法是 \"名字\" = 数值（名字带引号）；Add 成功返回下标、失败返回 -1"),
    _e("sw_set_global_variable", "doc", "IEquationMgr.Add(-1, expr)",
       "计数 0→1，Value 读回 5.0 且等式回读一致"),
    _e("sw_create_reference_axis", "doc", "IModelDoc2.InsertAxis2",
       "选前视+上视两个基准面 → RefAxis 0→1",
       "只选一个面时 InsertAxis2 返回 bool 但不出特征"),
]

# ── 视图/测量（2026-10-20 真机 3/3）────────────────────────────────
_VIEW_MEASURE: List[Tuple[str, ToolEntry]] = [
    _e("sw_zoom_to_fit", "view", "IModelDoc2.ViewZoomtofit2",
       "Scale2 可读且 > 0（实测 4.4976；刚建好就合适故不变化）"),
    _e("sw_set_view_orientation", "view", "IModelDoc2.ShowNamedView2",
       "Orientation 矩阵变化：0.884→0.707 / -0.240→-0.408 / 0.400→0.577"),
    _e("sw_measure_distance", "view", "IModelDocExtension.CreateMeasure",
       "40×25×20 方块的前后面距离 **20.0 mm**（期望 20，容差 0.2）",
       "pywin32 取不到 IMeasure 成员（找不到成员）→ 必须 comtypes"),
]

# ── 文档开关 / 配置（2026-10-20 真机 9/9）────────────────────────────
_CONFIG_IO: List[Tuple[str, ToolEntry]] = [
    _e("sw_open_document", "io", "ISldWorks.OpenDoc6", "文档数 0→1，标题 box_hole"),
    _e("sw_close_document", "io", "ISldWorks.CloseDoc", "文档数 2→1"),
    _e("sw_close_all", "io", "ISldWorks.CloseAllDocuments", "文档数 →0",
       "传 False 会被未保存提示卡住，实测要传 True"),
    _e("sw_save_all", "io", "ISldWorks.SaveAllDocuments", "无异常、文档数不变"),
    _e("sw_save_as_copy", "io", "IModelDoc2.SaveAs2(4 参)",
       "副本存在且**原文档路径不变**",
       "SaveAs4 有 5 参且 Errors/Warnings 是 byref，pywin32 报无效的参数数目"),
    _e("sw_list_configurations", "io", "IModelDoc2.GetConfigurationNames",
       "配置数 1（默认）+ 激活配置可读",
       "激活配置要走 ConfigurationManager.ActiveConfiguration.Name"),
    _e("sw_add_configuration", "io", "IModelDoc2.AddConfiguration3(4 参)", "配置数 1→2"),
    _e("sw_activate_configuration", "io", "IModelDoc2.ShowConfiguration2",
       "激活配置读回 == 目标",
       "返回值不可靠（切到已激活配置也返回 False），必须以读回为准"),
    _e("sw_get_referenced_documents", "io", "IModelDoc2.GetDependencies(2 参)",
       "图纸依赖 2 项（含 box_hole.SLDPRT）"),
]

# ── 钣金（2026-10-20 真机 3/4）──────────────────────────────────────
_SHEET_METAL: List[Tuple[str, ToolEntry]] = [
    _e("sw_base_flange", "sheet_metal", "IModelDoc2.InsertSheetMetalBaseFlange(9 参)",
       "特征 19→22，出现 SheetMetal + SMBaseFlange + FlatPattern",
       "BaseFlange 返回 None 但特征确实建出来了 —— 判据必须看特征树，不能看返回值"),
    _e("sw_get_flat_pattern_info", "sheet_metal", "IFeature(FlatPattern) + GetBodyBox",
       "FlatPattern 特征存在；GetBendState=1"),
    _e("sw_insert_bends", "sheet_metal", "IPartDoc.InsertBends(6 参)",
       "L 形等厚实体+选底面 → 特征 **SheetMetal+ProcessBends+FlatPattern**，bendState 0→**3**",
       "第 2 参是折弯表名字符串不是 bool；不选面时返回 True 但什么都不生成"),
    _e("sw_hem", "sheet_metal", "IModelDoc2.InsertSheetMetalHem(8 参)",
       "特征 22→23，特征树出现 Hem"),
]

# ── 文档级基础操作（2026-10-20 真机 7/8）────────────────────────────
_DOC_OPS: List[Tuple[str, ToolEntry]] = [
    _e("sw_connect", "doc", "Application.RevisionNumber", "版本 33.4.1 + 文档数可读"),
    _e("sw_create_part", "doc", "Application.NewDocument(.prtdot)", "GetType==1"),
    _e("sw_create_reference_plane", "doc", "IFeatureManager.InsertRefPlane",
       "RefPlane 3→4（基准面1）",
       "参考面在 pywin32 下只认选择类型 PLANE，不认 DATUMPLANE/BODYFEATURE"),
    _e("sw_select_entity", "doc", "IModelDocExtension.SelectByID2",
       "选择集 1"),
    _e("sw_clear_selection", "doc", "IModelDoc2.ClearSelection2", "选择集 1→0"),
    _e("sw_capture_screenshot", "doc", "IModelDocExtension.SaveAs(PNG)",
       "PNG 魔数 89504e47，125,249 B"),
    _e("sw_delete_feature", "doc", "IModelDocExtension.DeleteSelection2",
       "特征数 -1（删基准面1）"),
]

# ── 图纸补充（2026-10-20 真机 3/5）──────────────────────────────────
_DRAWING_EXTRA: List[Tuple[str, ToolEntry]] = [
    _e("sw_view_rotate", "drawing", "IDrawingDoc.DrawingViewRotate",
       "IView.Angle 0°→15°",
       "视图不能用 Select2 选，要 SelectByID2(name,'DRAWINGVIEW')"),
    _e("sw_export_drawing_pdf", "drawing", "IModelDoc2.SaveAs(PDF)",
       "109,332 B，%PDF-1.4"),
    _e("sw_export_drawing_dwg", "drawing", "IModelDoc2.SaveAs(DWG)",
       "36,478 B，AC1015（图纸导出比零件 DXF 可靠）"),
]

# ── 上游特征/导出族（2026-10-20 真机：拉伸 20000mm³ 精确；导出 4/6）────
_FEATURE_UPSTREAM: List[Tuple[str, ToolEntry]] = [
    _e("sw_extrude", "feature", "FeatureManager.FeatureExtrusion3",
       "40×25 草图 ×20mm → 体积 **20000.0 mm³**（手算一致，误差 0），实体 0→1"),
    _e("sw_export_step", "feature", "IModelDoc2.SaveAs(STEP)",
       "15,767 B，文件头 `ISO-10303-21`"),
    _e("sw_export_stl", "feature", "IModelDoc2.SaveAs(STL)",
       "684 B，二进制头 `stlbn`（80 字节头 + 三角面）"),
    _e("sw_export_file", "feature", "IModelDoc2.SaveAs(PDF)",
       "172,217 B，文件头 `%PDF-1.4`"),
    _e("sw_save_document", "feature", "IModelDoc2.SaveAs3/Save3",
       "原生 .SLDPRT 65,156 B 落盘"),
]

# ── 上游装配结构/状态族（2026-10-20 真机 11/11）────────────────────
_ASM_STATE: List[Tuple[str, ToolEntry]] = [
    _e("sw_create_assembly", "assembly", "Application.NewDocument(.asmdot)", "GetType==2"),
    _e("sw_insert_component", "assembly", "IAssemblyDoc.AddComponent5(8 参)",
       "组件 0→1→2；零件必须先打开，插入前要靠 ActivateDoc 切回装配",
       "ActivateDoc3 报类型不匹配，ActivateDoc(title) 单参版可用"),
    _e("sw_get_assembly_tree", "assembly", "GetComponents + IsFixed/IsSuppressed/IsHidden",
       "2 个组件，三个状态位全部可读"),
    _e("sw_suppress_component", "assembly", "IAssemblyDoc.SetComponentSuppression",
       "IsSuppressed False→True→False",
       "枚举反转：0=Suppressed、2=Resolved；不生效时退回 EditSuppress2"),
    _e("sw_hide_component", "assembly", "IAssemblyDoc.HideComponent/ShowComponent",
       "IsHidden False→True→False",
       "写 IComponent2.Visible 不改 IsHidden，必须用 Hide/ShowComponent"),
    _e("sw_replace_component", "assembly", "IAssemblyDoc.ReplaceComponents2(5 参)",
       "组件路径 box_hole.SLDPRT → box_off.SLDPRT"),
    _e("sw_suppress_feature", "feature", "IModelDoc2.EditSuppress2",
       "IsSuppressed False→True",
       "IsSuppressed2(0,None) 读回 None，不能当判据；EditSuppress2 是属性（读取即生效）"),
    _e("sw_unsuppress_feature", "feature", "IModelDoc2.EditUnsuppress2",
       "IsSuppressed True→False"),
]

# ── 上游 inspect 族（2026-10-20 真机 18/18）──────────────────────────
_INSPECT_UPSTREAM: List[Tuple[str, ToolEntry]] = [
    _e("sw_get_status", "inspect", "Application.RevisionNumber", "版本 33.4.1 + 文档数可读"),
    _e("sw_list_open_documents", "inspect", "Application.GetDocuments",
       "列表长度 == GetDocumentCount"),
    _e("sw_get_model_info", "inspect", "IModelDoc2.GetTitle/GetType",
       "标题=check_inspect、type=1、特征 22、实体 1"),
    _e("sw_list_features", "inspect", "IFeature.GetTypeName2", "22 个特征，名称全部非空"),
    _e("sw_get_mass_properties", "inspect", "IModelDocExtension.CreateMassProperty",
       "体积 5.921e-5 m³ = 59,215 mm³、质量 0.4737 kg、密度 8000",
       "pywin32 取不到 IMassProperty 成员（报找不到成员）→ 必须 comtypes"),
    _e("sw_list_bodies", "inspect", "IModelDoc2.GetBodies2", "实体 1 / 曲面 0"),
    _e("sw_get_custom_properties", "inspect", "GetCustomInfoNames2/CustomInfo2",
       "28 条属性名值成对可读（含中文名，如 零件号/单重）"),
    _e("sw_set_custom_property", "inspect", "IModelDoc2.AddCustomInfo3",
       "写 swkit_tag=r8-check 后 CustomInfo2 读回相等；属性数 28→29"),
    _e("sw_get_material", "inspect", "IModelDoc2.MaterialUserName/MaterialIdName", "可读"),
    _e("sw_set_material", "inspect", "IPartDoc.SetMaterialPropertyName2",
       "设 AISI 304 后 MaterialIdName 读回含 304"),
    _e("sw_rebuild_model", "inspect", "IModelDoc2.ForceRebuild3", "特征数 22→22 不变"),
    _e("sw_set_display_mode", "inspect", "IModelView.DisplayMode（可写属性）",
       "读回等于目标值",
       "没有 SetDisplayMode 方法（报 <unknown>.SetDisplayMode）——它是属性，赋值即可"),
    _e("sw_list_display_states", "inspect", "IConfiguration.GetDisplayStates",
       "列出 <默认>_显示状态 1"),
    _e("sw_get_dimension", "inspect", "IModelDoc2.Parameter → SystemValue", "读到 20.0 mm"),
    _e("sw_set_dimension", "inspect", "IDimension.SystemValue",
       "20→21 mm 读回一致，再恢复 20"),
]

# ── 上游 sketch 族（2026-10-20 真机转正：草图线段数判据）──────────────
_SKETCH_UPSTREAM: List[Tuple[str, ToolEntry]] = [
    _e("sw_create_sketch", "sketch", "SketchManager.InsertSketch",
       "12/12 次建草图成功，活动草图存在且线段 0"),
    _e("sw_edit_sketch", "sketch", "IModelDoc2.EditSketch",
       "选中草图后 EditSketch()，重入后 Name 匹配",
       "内核原用 MenuCommand(2026)，在本机报 <unknown>.MenuCommand —— 已改 API"),
    _e("sw_exit_sketch", "sketch", "SketchManager.InsertSketch(True)",
       "退出后 ActiveSketch 为 None（segments=-1）"),
    _e("sw_sketch_line", "sketch", "SketchManager.CreateLine", "线段 0→1"),
    _e("sw_sketch_circle", "sketch", "CreateCircleByRadius", "线段 0→1"),
    _e("sw_sketch_rectangle", "sketch", "CreateCornerRectangle", "线段 0→**4**"),
    _e("sw_sketch_arc", "sketch", "CreateArc", "线段 0→1"),
    _e("sw_sketch_ellipse", "sketch", "CreateEllipse", "线段 0→1"),
    _e("sw_sketch_polygon", "sketch", "CreatePolygon", "6 边形 → 线段 0→**7**"),
    _e("sw_sketch_spline", "sketch", "CreateSpline2（VT_ARRAY|VT_R8）",
       "4 个拟合点 → 线段 0→1",
       "内核 CreateSpline(list) 在 pywin32 下拿到空成员，必须传 COM 数组"),
    _e("sw_sketch_centerline", "sketch", "CreateLine + ConstructionGeometry",
       "线段 0→1（构造线）"),
]

_UNVERIFIED: List[Tuple[str, ToolEntry]] = [

    ("sw_dimxpert_autodim", ToolEntry("sw_dimxpert_autodim", "meta", "unverified",
        "IDimXpertPart.AutoDimensionScheme(option)", "",
        "实测返回 False、GetAnnotationCount 仍 0；需预设 PartType/ToleranceType 或先选要素")),

    ("sw_check_geometry", ToolEntry("sw_check_geometry", "feature", "broken",
        "(无公开 API)", "",
        "sldworks.tlb 只有 IModelDoc2.DebugCheckBody/DebugCheckIgesGeom，没有 CheckGeometry")),
    ("sw_add_section_view", ToolEntry("sw_add_section_view", "drawing", "unverified",
        "IDrawingDoc.CreateSectionViewAt", "",
        "图纸里没有\"前视基准面\"（剖视需在视图上画剖切线，不是选基准面）→ 找不到基准面")),

    ("sw_hide_all_planes", ToolEntry("sw_hide_all_planes", "view", "unverified",
        "IModelDoc2.SetUserPreferenceToggle", "",
        "swUserPreferenceToggle_e 里没有基准面/草图开关（实测仅 10 项：DisplayAxes/EntityPoints/…）")),
    ("sw_hide_all_sketches", ToolEntry("sw_hide_all_sketches", "view", "unverified",
        "IModelDoc2.SetUserPreferenceToggle", "", "同上：无对应枚举常量")),
    ("sw_show_all_sketches", ToolEntry("sw_show_all_sketches", "view", "unverified",
        "IModelDoc2.SetUserPreferenceToggle", "", "同上：无对应枚举常量")),
    ("sw_move_body", ToolEntry("sw_move_body", "body", "unverified",
        "IFeatureManager.InsertMoveCopyBody2(12 参)", "",
        "选中实体后三种参数解释（方向+距离 / 纯平移 / 距离字段）都无位移，包围盒 dx=0")),
    ("sw_combine_bodies", ToolEntry("sw_combine_bodies", "body", "unverified",
        "IFeatureManager.InsertCombineFeature(3 参)", "",
        "两次相交拉伸会被自动合并成 1 个体，当前夹具造不出两个可组合的体")),
    ("sw_split_body", ToolEntry("sw_split_body", "body", "unverified",
        "IFeatureManager.PreSplitBody/PostSplitBody2", "",
        "需要先有分割线/基准面且 PostSplitBody2 是 5 参，未尝试")),
    ("sw_sketch_extend", ToolEntry("sw_sketch_extend", "sketch", "unverified",
        "ISketchManager.SketchExtend(3 参)", "",
        "选中线段后调用，长度 20→20 不变（未知是否需要选端点或标记）")),
    ("sw_sketch_convert_entities", ToolEntry("sw_sketch_convert_entities", "sketch",
        "unverified", "ISketchManager.SketchUseEdge/SketchUseEdge2", "",
        "pywin32 报 DISP_E_PARAMNOTOPTIONAL；comtypes 下 SketchUseEdge() 无报错但线段数不变")),
    ("sw_unfold", ToolEntry("sw_unfold", "sheet_metal", "unverified",
        "IModelDoc2.InsertSheetMetalUnfold()", "",
        "平板无折弯时该动作无效果：特征 22→22、GetBendState 恒 1（需带折弯的钣金件才能验证）")),
    ("sw_fold", ToolEntry("sw_fold", "sheet_metal", "unverified",
        "IModelDoc2.InsertSheetMetalFold()", "", "同上：先要有展开态才谈折叠")),
    ("sw_edge_flange", ToolEntry("sw_edge_flange", "sheet_metal", "unverified",
        "InsertSheetMetalEdgeFlange(11 参)", "",
        "选 1 条边 + SketchFeat 传 None/none_dispatch 都返回 None；疑需法兰轮廓草图")),
    ("sw_miter_flange", ToolEntry("sw_miter_flange", "sheet_metal", "unverified",
        "InsertSheetMetalMiterFlange(11 参)", "", "同 edge_flange，需先有可选边集与轮廓")),
    ("sw_export_flat_pattern", ToolEntry("sw_export_flat_pattern", "sheet_metal",
        "unverified", "IModelDoc2.SaveAs(DXF)", "",
        "零件直接导 DXF 无输出（与 sw_export_dxf 同因：需工程图/展开图上下文）")),
    ("sw_add_equation", ToolEntry("sw_add_equation", "doc", "unverified",
        "IEquationMgr.Add", "",
        "IModelDoc2 没有 AddEquation；IEquationMgr 需 comtypes 强类型，pywin32 下 GetEquationMgr 报找不到成员")),
    ("sw_delete_equation", ToolEntry("sw_delete_equation", "doc", "unverified",
        "IEquationMgr.Delete", "", "同上，随 add_equation 一起待解")),
    ("sw_add_revision_table", ToolEntry("sw_add_revision_table", "drawing", "unverified",
        "ISheet.InsertRevisionTable2(7 参)", "",
        "空模板与真实 .sldrevtbt 模板都返回 None，RevisionTable 仍为 None（SW2025 此上下文不可用）")),
    ("sw_add_detail_view", ToolEntry("sw_add_detail_view", "drawing", "unverified",
        "IDrawingDoc.CreateDetailViewAt3(9 参)", "",
        "返回 None、视图数不变：详图需要父视图上已有详图圆（detail circle）")),
    # ── 特征族里没打通/不可验证的（2026-10-20 实测依据）──────────────
    ("sw_revolve", ToolEntry("sw_revolve", "feature", "unverified",
        "FeatureManager.FeatureRevolve2", "",
        "TLB 显示 5 参、内核按 12 参调，两边都报 DISP_E_PARAMNOTOPTIONAL（真实参数列表未定）")),


    ("sw_hole_wizard", ToolEntry("sw_hole_wizard", "feature", "unverified",
        "HoleWizard5", "",
        "该 API 需 **27 个参数**，内核只传 14 个 → DISP_E_PARAMNOTOPTIONAL")),
    ("sw_mirror", ToolEntry("sw_mirror", "feature", "unverified",
        "InsertMirrorFeature2(5 参)", "",
        "特征(选中 2 个对象)+基准面(mark 32)都选好后仍返回 None")),
    ("sw_export_iges", ToolEntry("sw_export_iges", "feature", "unverified",
        "IModelDoc2.SaveAs(IGES)", "",
        "调用不报错但文件根本没生成（0 字节/不存在）")),
    ("sw_export_dxf", ToolEntry("sw_export_dxf", "feature", "unverified",
        "IModelDoc2.SaveAs(DXF)", "",
        "零件直接导 DXF 无输出（DXF 需工程图或展开图上下文）")),

    ("sw_sketch_circular_pattern", ToolEntry("sw_sketch_circular_pattern", "sketch",
        "unverified", "CreateCircularSketchStepAndRepeat", "",
        "comtypes 要求 RadiusDim 等尺寸对象参数")),


    ("sw_flow_project",
     ToolEntry("sw_flow_project", "meta", "unverified", "EFDApi.IDocument.CreateProject",
               "返回 IProject 对象，但 GetProjectsCount 仍 0 —— 工程没进列表",
               "整轮求解需先配边界条件/目标/网格，再 ApplyCalculationControlOptions")),
]

# 注意：上表刻意保留重复键时的"后写覆盖"语义，避免手抖写重时静默丢条目。
REGISTRY: Dict[str, ToolEntry] = {}
for _name, _entry in (_VERIFIED + _STUDY_META + _SKETCH_UPSTREAM
                     + _INSPECT_UPSTREAM + _ASM_STATE + _FEATURE_UPSTREAM
                     + _DOC_OPS + _DRAWING_EXTRA + _SHEET_METAL + _CONFIG_IO + _VIEW_MEASURE + _EQUATIONS + _SKETCH_EDIT + _BODIES + _CUTS + _SURFACES + _DRAWING_VIEWS
                     + _UNSTABLE
                     + _UNVERIFIED + _BROKEN):
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
    "sw_add_weld_symbol", "sw_note", "sw_add_annotation", "sw_add_surface_finish",
    "sw_add_auxiliary_view", "sw_create_section_view", "sw_add_broken_view",
    "sw_add_drawing_dimension", "sw_add_hole_table", "sw_add_balloon",
    # 装配其余（verified/asm_ops.py，2026-10-20 真机 4/4，含干涉 A/B）
    "sw_check_interference", "sw_fix_component", "sw_show_all_components",
    "sw_explode_assembly", "sw_move_component",
    # 图纸视图/BOM（verified/drawing_extra.py，2026-10-20 真机 2/3）
    "sw_add_drawing_view", "sw_add_bom_table",
    # 曲面（verified/surfaces.py，2026-10-20 真机 3/3）
    "sw_planar_surface", "sw_revolved_surface", "sw_extruded_surface",
    # 切除（verified/cuts.py，2026-10-20 真机 3/3）
    "sw_cut_extrude",
    # 实体级操作（verified/bodies.py，2026-10-20 真机 2/2）
    "sw_scale_body", "sw_delete_body",
    # 草图编辑（verified/sketch_edit.py，2026-10-20 真机 4/4）
    "sw_sketch_trim", "sw_sketch_fillet", "sw_sketch_chamfer", "sw_start_3d_sketch",
    "sw_sketch_offset", "sw_sketch_linear_pattern",
    # 方程/全局变量/参考轴（verified/equations.py，2026-10-20 真机 4/4）
    "sw_get_equations", "sw_list_global_variables", "sw_set_global_variable",
    "sw_create_reference_axis",
    # 视图/测量（verified/view_measure.py，2026-10-20 真机 3/3）
    "sw_zoom_to_fit", "sw_set_view_orientation", "sw_measure_distance",
    # 文档开关 / 配置（verified/config_io.py，2026-10-20 真机 9/9）
    "sw_open_document", "sw_close_document", "sw_close_all", "sw_save_all",
    "sw_save_as_copy", "sw_list_configurations", "sw_add_configuration",
    "sw_activate_configuration", "sw_get_referenced_documents",
    # 钣金（verified/sheet_metal.py，2026-10-20 真机 3/4）
    "sw_base_flange", "sw_get_flat_pattern_info", "sw_hem", "sw_insert_bends",
    # 文档级基础操作（verified/doc_ops.py，2026-10-20 真机 7/8）
    "sw_connect", "sw_create_part", "sw_create_reference_plane", "sw_select_entity",
    "sw_clear_selection", "sw_capture_screenshot", "sw_delete_feature",
    # 图纸补充（verified/drawing_extra.py，2026-10-20 真机 3/5）
    "sw_view_rotate", "sw_export_drawing_pdf", "sw_export_drawing_dwg",
    # 上游特征/导出族（verified/features.py、verified/io_export.py，2026-10-20）
    "sw_extrude", "sw_chamfer", "sw_fillet", "sw_analyze_draft", "sw_export_step", "sw_export_stl", "sw_export_file",
    "sw_save_document",
    # 上游装配结构/状态族（verified/asm_state.py，2026-10-20 真机 11/11）
    "sw_create_assembly", "sw_insert_component", "sw_get_assembly_tree",
    "sw_suppress_component", "sw_hide_component", "sw_replace_component",
    "sw_suppress_feature", "sw_unsuppress_feature",
    # 上游 inspect 族（verified/inspect.py，2026-10-20 真机 18/18）
    "sw_get_status", "sw_list_open_documents", "sw_get_model_info", "sw_list_features",
    "sw_get_mass_properties", "sw_list_bodies", "sw_get_custom_properties",
    "sw_set_custom_property", "sw_get_material", "sw_set_material", "sw_rebuild_model",
    "sw_set_display_mode", "sw_list_display_states", "sw_get_dimension", "sw_set_dimension",
    # 上游 sketch 族（verified/sketch_ops.py，2026-10-20 真机 11/11）
    "sw_create_sketch", "sw_edit_sketch", "sw_exit_sketch", "sw_sketch_line",
    "sw_sketch_circle", "sw_sketch_rectangle", "sw_sketch_arc", "sw_sketch_ellipse",
    "sw_sketch_polygon", "sw_sketch_spline", "sw_sketch_centerline",
    # 草图 / 文档级（verified/sketch.py、verified/model.py，2026-10-20 真机 5/5）
    "sw_sketch_construction", "sw_sketch_text", "sw_add_sketch_constraint",
    "sw_activate_display_state", "sw_list_materials", "sw_dxp", "sw_flow_check",
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
