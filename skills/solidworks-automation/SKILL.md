---
name: solidworks-automation
description: >
  用 swkit 在本机 SolidWorks 2025 上做零件/装配/工程图自动化，并**用几何判据验证结果**。
  当用户要求建模（拉伸/旋转/切除/圆角/倒角/阵列/镜像/抽壳/分割）、装配（插组件、
  配合、干涉检查、抑制/隐藏）、钣金、出图（视图/标注/孔表/注释）、导出
  STEP/STL/IGES/PDF/DXF，或问"某个 SolidWorks 工具能不能用 / 为什么没效果"时使用。
  内含：实测通过的 API 配方、必须检查的判据、以及已证伪不可用的能力清单
  （避免重复试错）。Use for SolidWorks automation, CAD modeling/assembly/drawing
  pipelines, geometry-verified CAD edits, and diagnosing silent no-op COM calls.
---

# SolidWorks 自动化（swkit）

## 这个技能解决什么

SolidWorks 的 COM API 有一批**反直觉**的地方：同一个功能有"存在但已废弃"的方法，
选择标记对组件和特征刚好相反，某些成员是属性而不是方法，某些数组会被 COM 绑定
**静默丢弃**。结果就是：**调用不报错、也没有效果**（本仓库称之为"假成功"）。

这个技能把这些坑固化成了三条东西：**配方**（怎么调）、**判据**（怎么证明成功了）、
**证伪清单**（哪些根本别试）。

## 开工前 30 秒

1. `swkit status` —— 确认连上了、SW 版本、当前文档。
2. `swkit registry --implemented` —— **只用这张表**（有实现、有真机判据）。
   表里没有的能力，要么是 `unverified`（可试，但必须自己补判据），
   要么是 `broken`（别再试）。**不要凭记忆猜 API 签名。**
3. 动手前先想清楚判据：这次改动应该让**体积 / 面数 / 边数 / 实体数 / 包围盒 /
   文件签名**中的哪一个变化？说不出来就先别调。

## 铁律（违反必踩坑）

| 铁律 | 原因 / 证据 |
|---|---|
| **判据用几何量，不用返回值** | `CreateAuxiliaryView()`→None、`InsertSplitLineProject()`→0、`InsertSheetMetalBaseFlange`→None 全都成功；`AddComponent`→True 却什么都没插 |
| **属性 vs 方法**：`GetDefinition` / `PreSplitBody2` / `GetBendState` / `GetProcessID` / 方程的 `GetCount` 都是**属性或方法要看绑定** | pywin32 与 comtypes 不一样；判别用 `isinstance(node, types.MethodType)`，**不要**用 `callable()`（`CDispatch` 本身可调用） |
| **`None` ≠ 空 `IDispatch`** | 可选对象参数要 `none_dispatch()`；传 `None`/`0` 报"类型不匹配"（`SelectByID2` 的 Callout、`InsertCombineFeature` 的 MainBody） |
| **输出参数要 `VARIANT(VT_BYREF\|VT_I4)`** | `SaveAs4` 的 Errors/Warnings 传 `0` 直接类型不匹配 |
| **选择标记**：特征阵列 特征=4/方向=1；组件阵列 组件=1/方向=2,4；镜像特征 面=2；镜像实体 实体=256 | 用反了必然 no-op；两种阵列的标记**刚好相反** |
| **`ClearSelection2` 在 `IModelDoc2`** | 不在 `IModelDocExtension` 上 |
| **`IModelDoc2` 不能直接 QI 成 `IFeatureManager`** | 要用 `md.FeatureManager` 再 QI |
| **单位混用**：`SelectByID2` 坐标、`InsertMoveCopyBody2` 的 TransX/Y/Z 是**米**；`InsertComponent` 是**毫米** | 装错会让干涉检查把"分开的零件"报成干涉 |
| **导出必须验文件签名** | IGES 只认 `.igs`（`.iges` 会**静默 0 字节**）；STEP=`ISO-10303-21`、PDF=`%PDF`、STL=`solid`/`stlbn` |
| **装配前先把零件 `OpenDoc` 打开** | `AddComponent5` 在零件未打开时**静默返回 None**；打开后 `ActiveDoc` 会变成零件，必须**先记住装配体引用** |
| **跑批处理前 `CloseAllDocuments(True)`** | 否则文件被占用 → `WinError 32` 整轮中断 |
| **`-2147417851 服务器出现意外情况`** | 大概率 SW "假活"；先把 `SLDEXITAPP` 错误窗口关掉再重试 |

## 怎么执行

CLI 与 MCP 暴露的是同一批实现；脚本里用 CLI 更省上下文，Agent 里用 MCP 更直接。

```bash
swkit status                              # 连接/版本/当前文档
swkit registry --implemented              # 只用这张表
swkit new-part                            # 新建零件
swkit sketch --plane 前视基准面 --rect 0 0 80 50
swkit extrude --depth 10                  # 判据：体积 0→40000 mm³
swkit mass                                # 读体积/面积/重心
```

## 能力索引

<!-- gen:capabilities:BEGIN -->
本表由 `tools/gen_skill_capabilities.py` 从 `src/swkit/registry.py` 生成，**不要手改**（`tests/test_offline.py::test_skill_matches_registry` 会校验）。

共 **150** 个 verified 工具。想看完整状态（含不稳/未打通/判死）：`swkit registry`。

| 能力族 | 工具 |
|---|---|
| **草图**（22） | `sw_add_sketch_constraint` `sw_create_sketch` `sw_edit_sketch` `sw_exit_sketch` `sw_sketch_arc` `sw_sketch_centerline` `sw_sketch_chamfer` `sw_sketch_circle` `sw_sketch_circular_pattern` `sw_sketch_construction` `sw_sketch_convert_entities` `sw_sketch_ellipse` `sw_sketch_fillet` `sw_sketch_line` `sw_sketch_linear_pattern` `sw_sketch_offset` `sw_sketch_polygon` `sw_sketch_rectangle` `sw_sketch_spline` `sw_sketch_text` `sw_sketch_trim` `sw_start_3d_sketch` |
| **出图**（20） | `sw_add_annotation` `sw_add_auxiliary_view` `sw_add_balloon` `sw_add_bom_table` `sw_add_broken_view` `sw_add_center_mark` `sw_add_centerline` `sw_add_datum_feature` `sw_add_drawing_dimension` `sw_add_drawing_view` `sw_add_gtol` `sw_add_hole_table` `sw_add_surface_finish` `sw_add_weld_symbol` `sw_create_section_view` `sw_export_drawing_dwg` `sw_export_drawing_pdf` `sw_note` `sw_take_photoview_screenshot` `sw_view_rotate` |
| **特征**（20） | `sw_analyze_draft` `sw_chamfer` `sw_circular_pattern` `sw_cut_extrude` `sw_export_file` `sw_export_step` `sw_export_stl` `sw_extrude` `sw_fillet` `sw_linear_pattern` `sw_mirror` `sw_mirror_feature` `sw_offset_surface` `sw_revolve` `sw_save_document` `sw_shell` `sw_split_line` `sw_suppress_feature` `sw_thicken_surface` `sw_unsuppress_feature` |
| **只读检查**（15） | `sw_get_custom_properties` `sw_get_dimension` `sw_get_mass_properties` `sw_get_material` `sw_get_model_info` `sw_get_status` `sw_list_bodies` `sw_list_display_states` `sw_list_features` `sw_list_open_documents` `sw_rebuild_model` `sw_set_custom_property` `sw_set_dimension` `sw_set_display_mode` `sw_set_material` |
| **装配**（14） | `sw_check_interference` `sw_create_assembly` `sw_explode_assembly` `sw_fix_component` `sw_get_assembly_tree` `sw_hide_component` `sw_insert_component` `sw_mirror_component` `sw_move_component` `sw_pattern_component_circular` `sw_pattern_component_linear` `sw_replace_component` `sw_show_all_components` `sw_suppress_component` |
| **文档级**（13） | `sw_add_equation` `sw_capture_screenshot` `sw_clear_selection` `sw_connect` `sw_create_part` `sw_create_reference_axis` `sw_create_reference_plane` `sw_delete_equation` `sw_delete_feature` `sw_get_equations` `sw_list_global_variables` `sw_select_entity` `sw_set_global_variable` |
| **元数据/元工具**（12） | `sw_activate_display_state` `sw_dxp` `sw_get_bounding_box` `sw_list_materials` `sw_ovba_dump` `sw_ovba_selftest` `sw_props` `sw_scan` `swdm_bom` `swdm_query` `swdm_stats` `swdm_tables` |
| **导入导出**（10） | `sw_activate_configuration` `sw_add_configuration` `sw_close_all` `sw_close_document` `sw_export_iges` `sw_get_referenced_documents` `sw_list_configurations` `sw_open_document` `sw_save_all` `sw_save_as_copy` |
| **仿真/运动**（10） | `sw_motion_list` `sw_motion_read` `sw_sim_addin_check` `sw_sim_faces` `sw_sim_mesh` `sw_sim_read` `sw_sim_run` `sw_sim_setup` `sw_sim_solve` `sw_sim_status` |
| **实体**（4） | `sw_combine_bodies` `sw_delete_body` `sw_move_body` `sw_scale_body` |
| **钣金**（4） | `sw_base_flange` `sw_get_flat_pattern_info` `sw_hem` `sw_insert_bends` |
| **曲面**（3） | `sw_extruded_surface` `sw_planar_surface` `sw_revolved_surface` |
| **视图**（3） | `sw_measure_distance` `sw_set_view_orientation` `sw_zoom_to_fit` |
<!-- gen:capabilities:END -->

## 别试这些（已证伪或未打通，做了也是白做）

<!-- allow:non-verified:BEGIN -->
| 能力 | 状态 | 实测结论 |
|---|---|---|
| `sw_hole_wizard` | 未打通 | 官方 27 参全齐仍返回 None、体积不变；本仓库**没有** verified 的螺纹孔工具，需要时手工组合「底孔 `sw_cut_extrude` + 倒角 `sw_chamfer`」并自补判据 |
| `sw_edge_flange` / `sw_miter_flange` | 未打通 | 能建出**空特征**：轮廓草图 0 段 0 点、`IEdgeFlangeFeatureData` 没有 Length → 几何为零 |
| `sw_split_body` | 未打通 | `PreSplitBody2` 能算出 2 个分割体，但 `PostSplitBody2` 六种封装全返回 None、实体数恒 1 |
| `sw_sketch_extend` | 未打通 | `SketchExtend(X,Y,Z)` 是**目标点坐标**（不是选线段）；选线段/选端点都恒返回 False |
| `sw_fold` / `sw_unfold` | 未打通 | 真带折弯件（含 `ProcessBends`）上 4 种选择组合全返回 None，几何不变 |
| `sw_dimxpert_autodim` | 未打通 | `AutoDimensionScheme` 返回 False、标注数仍 0；**读取侧 `sw_dxp` 是通的** |
| `sw_delete_face` | 判死 | `DeleteFaces3` 的 option×flag 10 组全 `(False, False)` |
| `sw_knit_surfaces` / `sw_check_geometry` | 判死 | 类型库里**没有**对应方法（只有别的特征的 `Knit` 属性） |
| `sw_start_macro_recording` / `sw_stop_macro_recording` | 判死 | 类型库穷举无 `StartRecording`/`StopRecording` |
| `sw_hide_all_planes` / `sw_show_all_planes` / `sw_hide_all_sketches` / `sw_show_all_sketches` | 判死/不稳 | `swUserPreferenceToggle_e` 里没有基准面/草图开关；`UnblankRefGeom` 判据不立 |
| `sw_add_detail_view` | 未打通 | 全类型库扫描确认**没有**任何 Create/Insert/Add DetailCircle 方法 → 详图圆只能交互创建 |
| `sw_add_section_view` / `sw_add_revision_table` | 未打通 | 剖视需在视图上画剖切线；修订表 3 模板×2 API 全 None（已排除缺图纸格式） |
| `sw_export_dxf` / `sw_export_flat_pattern` | 未打通 | 零件直接导 DXF 无输出，需要工程图或展开图上下文 |
| `sw_flow_check` | 环境依赖 | 需 **Flow Simulation 插件**在当前会话已加载；未加载时 attach 抛 E_FAIL（会给出提示并 SKIP） |
<!-- allow:non-verified:END -->

逐条证据与最小复现见仓库 `docs/SILENT_FAILURES.md`。

## 典型任务配方

### 建模 + 判据

```bash
swkit new-part
swkit sketch --plane 前视基准面 --rect 0 0 40 25
swkit extrude --depth 20          # 判据：体积 20000 mm³（可手算对照）
# 圆角/倒角走 MCP sw_fillet / sw_chamfer（CLI 暂无对应子命令）
swkit mass                        # 读回核对
```

通孔必须在**顶面**开草图，不能在基准面画圆后直接切：

```python
doc.Extension.SelectByID2("", "FACE", 0.040, 0.025, 0.010, False, 0, none_dispatch(), 0)
doc.SketchManager.InsertSketch(True); S.circle(doc, 40, 25, 5); doc.SketchManager.InsertSketch(True)
选中最新的 SKETCH 要素后 -> cuts.cut_extrude(doc, through_all=True)
```

### 装配（三个必做动作）

```python
asm = 记住 create_assembly() 后的 ActiveDoc   # 不要之后从 ActiveDoc 再取
for p in (partA, partB): app.OpenDoc(p, 1)     # 必须预打开
r1 = insert_component(asm, partA, 0, 0, 0, fixed=True)
r2 = insert_component(asm, partB, 130, 0, 0)   # 分开 130mm
check_interference(asm)                        # 判据：count=0 也算成功
```

### 出图

```python
drawing.new_drawing(part, view="front")   # 中文模板只认 *前视
view = drawing.first_model_view(dwg)
drawing.note(dwg, "技术要求…"); drawing.drawing_dimension(dwg)
```

出图类 API 返回值几乎都不可信，判据一律用**对应集合的计数**
（`GetCenterMarks` / `GetDatumTagCount` / `GetGTolCount` / `GetSFSymbols` /
`GetDisplayDimensions` / `GetBreakLines`）。`None` 常常是"0 个"，不是"没有判据"。

### 导出

```bash
swkit export --kind step --path D:/out/part.step    # 判据：ISO-10303-21
swkit export --kind iges --path D:/out/part.igs     # 只认 .igs
```

### 参数与方程

```python
from swkit.verified import doc_ops as DO
DO.add_equation(doc, '"W" = 40')   # 判据：计数 +1 且 Equation(0) 读回一致
```

## 方法论（审查与交付）

工程图/DFM/自审查的**检查方法**见 [`references/methodology.md`](references/methodology.md)，
装配类任务的检查清单见 [`references/checklists.md`](references/checklists.md)。

要点：swkit 能**可靠执行并证明**几何变化，但 **GB/T 图面审查、DFM 判断、公差链**
目前是**人/模型按方法论检查**，不是 API 自动化——不要把它说成"已自动化"。

## 需要细节时读这些

| 文件 | 内容 |
|---|---|
| `docs/PITFALLS.md` | 逐条踩坑记录，改代码前扫一遍 |
| `docs/SILENT_FAILURES.md` | "返回成功但几何不动"的完整清单（含最小复现） |
| `docs/RECIPES.md` | 完整配方（组件阵列、镜像、螺纹孔、截图、插组件） |
| `docs/UNSUPPORTED.md` | 状态表（由 registry 生成），别重复试 |
| `references/methodology.md` | 出图审查 / DFM / 自审查的检查方法 |
| `references/checklists.md` | 装配类任务的事前/事中/验收清单 |

## 交付前的自检三问

1. **数字变了吗？** 体积/面数/边数/实体数/组件数/符号数，至少一个有可复现的前后对比。
2. **语义标志位对吗？** 阵列实例看 `IsPatternInstance`，镜像看 `IsMirrored`，
   螺纹看 `ThreadFeatureData` 的 Type/Pitch/Size。
3. **负面对照做过吗？** 把关键参数（标记、方向、类型）换成已知错误值，应该失败。
   不能失败的判据，通常也证明不了成功。
