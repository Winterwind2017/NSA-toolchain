# UNSUPPORTED —— 用不了的东西，以及为什么

> 这个文件的存在意义：**避免下一轮再去试同一件事**。
> 每条都写了"试过什么、结果是什么、为什么判定不行"。

判定口径：

- `broken` —— 有明确证伪依据（类型库无该方法 / 参数横扫全失败）
- `unstable` —— 曾成功，但会挂起/崩溃，或不具备可构造的判据

> 「调用返回成功、几何量却不动」这一类（最危险，容易被误判成成功）统一收录在
> [`SILENT_FAILURES.md`](SILENT_FAILURES.md)：逐项证据、共性教训、以及将来可用来复核的测试清单。

> **本文件的三个状态章节由 `tools/gen_unsupported.py` 从 `src/swkit/registry.py` 生成，
> 请勿手改**；改结论请改 registry 的 note，再重跑该脚本。
> `tests/test_offline.py::test_unsupported_doc_matches_registry` 会校验两者一致。

---

## broken —— 有明确证伪依据（5 条）

### `sw_check_geometry`（feature）

- API：`(无公开 API)`
- 结论：sldworks.tlb 只有 IModelDoc2.DebugCheckBody/DebugCheckIgesGeom，没有 CheckGeometry

### `sw_delete_face`（feature）

- API：`IBody2.DeleteFaces3`
- 结论：换 VARIANT(VT_ARRAY|VT_DISPATCH) 传数组同样无效

### `sw_knit_surfaces`（feature）

- API：`（无）`
- 结论：只有 IMirrorSolidFeatureData.KnitSurface / IPartingSurfaceFeatureData.Knit 这类别的特征的属性

### `sw_start_macro_recording`（meta）

- API：`（无）`
- 结论：含 record/macro 的只有 InsertMacroFeature*/IJournalManager.WriteJournalToMacro

### `sw_stop_macro_recording`（meta）

- API：`（无）`
- 结论：同上

## unstable —— 不进自动回归（3 条）

### `sw_add_sketch_dimension`（sketch）

- API：`AddAlongXDimension mark=1`
- 结论：不进自动回归；调用方需自行超时保护

### `sw_flow_check`（meta）

- API：`EFDApiSrv.EFDLauncher.Attach2RunningCADInstance + EFDApi.IApplication`
- 结论：依赖 **Flow Simulation 插件已在当前 SW 会话中加载**：插件未加载时 attach 抛 E_FAIL(0x80004005)，已改为给出可执行提示并标 addin_loaded=False；插件加载时实测版本 Flow Simulation 2025 SP3.0 Build 6784、静默 True、工程数 0。tests/flow_check.py 在插件未加载时整体 SKIP

### `sw_show_all_planes`（meta）

- API：`UnblankRefGeom`
- 结论：判据未立，不宜宣称已修

## unverified —— 已登记但没打通（17 条）

### `sw_add_detail_view`（drawing）

- API：`IDrawingDoc.CreateDetailViewAt3(9 参)`
- 结论：`CreateDetailViewAt3(9 参)` / `At4(12 参)` 在无详图圆时都返回 None、视图数不变；而**全类型库扫描确认没有任何 Create/Insert/Add DetailCircle 方法**（IView 只有 GetDetailCircle* 读取类）→ 详图圆只能交互创建，在图纸上画圆再用 SelectByID2 选 SKETCHSEGMENT 也选不中

### `sw_add_revision_table`（drawing）

- API：`ISheet.InsertRevisionTable2(7 参)`
- 结论：已用**真实模板全路径**重试（`lang/chinese-simplified/standard revision block.sldrevtbt`、英文 `no zone column.sldrevtbt`、空模板）与两种 API（InsertRevisionTable 5 参 / InsertRevisionTable2 7 参）：自由放置模式全返回 None；锚点模式（UseAnchorPoint=True, AnchorType 1-3）虽返回 `_Dispatch`，但其 Shape/Name/IsActive 全是 None，且 `ISheet.RevisionTable` 仍为 None、表格标注数读不到 —— 图纸本身有格式（`a3 - gb.slddrt`），所以不是缺格式

### `sw_add_section_view`（drawing）

- API：`IDrawingDoc.CreateSectionViewAt`
- 结论：图纸里没有"前视基准面"（剖视需在视图上画剖切线，不是选基准面）→ 找不到基准面

### `sw_dimxpert_autodim`（meta）

- API：`IDimXpertPart.AutoDimensionScheme(option)`
- 结论：实测返回 False、GetAnnotationCount 仍 0；需预设 PartType/ToleranceType 或先选要素

### `sw_edge_flange`（sheet_metal）

- API：`IModelDoc2.InsertSheetMetalEdgeFlange(11 参)`
- 结论：能**建出空特征**：InsertSketchForEdgeFlange 先造草图8（第 2 参必须传**草图特征对象**，传名字报类型不匹配），再 InsertSheetMetalEdgeFlange 得到 EdgeFlange 特征，但体积 4800→4800、面 6→6 不变。根因：InsertSketchForEdgeFlange 造的轮廓草图是空的（0 段 0 点），而 IEdgeFlangeFeatureData 没有 Length、长度只来自该草图 → 零几何；SetBendState 0/1/2/3 与重建都无效；改 OffsetType 报 RPC_E_SERVERFAULT。详见 docs/SHEET_METAL_NOTES.md

### `sw_export_dxf`（feature）

- API：`IModelDoc2.SaveAs(DXF)`
- 结论：零件直接导 DXF 无输出（DXF 需工程图或展开图上下文）

### `sw_export_flat_pattern`（sheet_metal）

- API：`IModelDoc2.SaveAs(DXF)`
- 结论：零件直接导 DXF 无输出（与 sw_export_dxf 同因：需工程图/展开图上下文）

### `sw_flow_project`（meta）

- API：`EFDApi.IDocument.CreateProject`
- 结论：整轮求解需先配边界条件/目标/网格，再 ApplyCalculationControlOptions

### `sw_fold`（sheet_metal）

- API：`IModelDoc2.InsertSheetMetalFold()`
- 结论：同上：先要有展开态才谈折叠

### `sw_hide_all_planes`（view）

- API：`IModelDoc2.SetUserPreferenceToggle`
- 结论：swUserPreferenceToggle_e 里没有基准面/草图开关（实测仅 10 项：DisplayAxes/EntityPoints/…）

### `sw_hide_all_sketches`（view）

- API：`IModelDoc2.SetUserPreferenceToggle`
- 结论：同上：无对应枚举常量

### `sw_hole_wizard`（feature）

- API：`IFeatureManager.HoleWizard5(27 参)`
- 结论：按官方示例 27 参调用（swWzdHole=2/AnsiMetric=1/Pan=32/M6/贯穿），选顶面或选基准面都返回 None、体积 48000→48000 不变 —— 孔向导对本机不可用；它也不解析规格表（恒 Ø50.8）。本机没有 `sw_threaded_hole`，螺纹孔按 `docs/RECIPES.md` §3 配方做。

### 螺纹孔（`sw_threaded_hole` 已可用，2026-11-06）

`sw_threaded_hole` 现在是**真工具**（verified，见 registry 与 `docs/RECIPES.md` §3）。
`sw_hole_wizard` 的判据已改成"体积反算孔径 vs 规格表"，比不过即判失败；
它就是按下面这条配方实现的（配方本身留作排障依据）：
底孔 `FeatureCut4` → 口部 `InsertFeatureChamfer` → `CreateDefinition(87=swFmSweepThread)`
+ `ThreadFeatureData`（`edge.Select2(False, 1)`，Type="Metric Tap"）。

### `sw_miter_flange`（sheet_metal）

- API：`InsertSheetMetalMiterFlange(11 参)`
- 结论：同 edge_flange，需先有可选边集与轮廓

### `sw_show_all_sketches`（view）

- API：`IModelDoc2.SetUserPreferenceToggle`
- 结论：同上：无对应枚举常量

### `sw_sketch_extend`（sketch）

- API：`ISketchManager.SketchExtend(X, Y, Z)`
- 结论：3 个参数是**目标点坐标**（不是选线段）；选线段或选端点都返回 **False**、线段长度 10→10 mm 不变。见 tests/split_extend_check.py

### `sw_split_body`（body）

- API：`IFeatureManager.PreSplitBody2（属性）/ PostSplitBody2(5 参)`
- 结论：PreSplitBody2 是**属性**且能算出 **2** 个分割体（刀具被识别），但 PostSplitBody2 在 6 种封装下全返回 None 且实体数恒为 1：ConsumeCut True/False、BodiesToMark 传 tuple/list/VARIANT/单个体、Origins+SavePaths 用长度匹配的空数组或真实存盘路径都无效；swFm(132) 里也没有 split 定义 id，无法走 CreateDefinition。见 tests/split_extend_check.py

### `sw_unfold`（sheet_metal）

- API：`IModelDoc2.InsertSheetMetalUnfold()`
- 结论：已用 insert_bends 造的**真带折弯件**重测（bend_state=3，含 ProcessBends/FlattenBends/FlatPattern）：4 种选择组合（不选/只边/面+边）都返回 None —— “面+边”会多出一个特征但体积 68000、包围盒 100×80×40 完全不变；空特征而非几何

---

## 计数校验

| 状态 | 条数 |
|---|---|
| `broken` | 5 |
| `unstable` | 3 |
| `unverified` | 17 |

> 与 `swkit.registry.summary()` 一致；不一致时离线测试会失败。

---

# 人工补充（不随 registry 生成）

> 下面这些是历史调查笔记，内容不来自 registry，因此保留为手工维护。

## 上游实现里"根本不存在的方法"

这些是 [Solidworks-MCP-Server](https://github.com/Eduardof0nt/Solidworks-MCP-Server)
（MIT，作者 Eduardo Font Cruz）里写错的地方，本仓库已按实测配方重写：

| 上游调用 | 事实 | 本仓库做法 |
|---|---|---|
| `IFeatureManager.LocalLinearComponentPattern` | `sldworks.tlb` 里**不存在** | `FeatureLinearPattern5` + 组件 mark=1 / 方向 mark=2 |
| `IFeatureManager.LocalCircularComponentPattern` | 同上 | `FeatureCircularPattern5` + 同样标记 |
| `IFeatureManager.InsertMirrorComponents2` | 同上 | `CreateDefinition(116)` + `IMirrorComponentFeatureData` + `CreateFeature` |
| `IAssemblyDoc.MirrorComponents3` | 存在，但 SW2025 文档标注 **Obsolete**，实测 no-op | 同上 |

---

## 还没复核的工具

上游另有约 44 个工具（`sw_*`）本仓库**尚未逐个复核**。它们通过
`sw_api(op, params)` 透传可用，但响应恒带 `"status": "unverified"`。
迁移计划见 [`MIGRATION.md`](MIGRATION.md)。

---


## 勘误：`sw_add_surface_finish` 曾被误降级（已恢复 verified）

2026-10-20 我先把它从 verified 降到 unverified，理由是"插入只返回 True、IView 没有
粗糙度 getter"。**这个结论是错的**，错在测量条件：

| 条件 | `GetSFSymbols` 返回 | 我的误读 |
|---|---|---|
| 视图**未激活** | `None` | 当成"没有这个 getter"→ 判据不可得 |
| 视图**已激活**（`ActivateView`） | 插入前 0、插入后 1 | 真正可计数 |

所以正确做法是：**先 `ActivateView` 再插入，用 `GetSFSymbols` 的 0→1 做判据**。
代码已按此修正（`None` 一律当 0），并恢复 verified。

教训：**"取不到数"和"没有判据"是两件事**。遇到 `None` 要先换条件重测（激活视图、换视图类型、
换选择标记），再决定降级。这条比任何一条 API 坑都值钱。
