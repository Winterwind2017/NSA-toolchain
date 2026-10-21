# UNSUPPORTED —— 用不了的东西，以及为什么

> 这个文件的存在意义：**避免下一轮再去试同一件事**。
> 每条都写了"试过什么、结果是什么、为什么判定不行"。

判定口径：

- `broken` —— 有明确证伪依据（类型库无该方法 / 参数横扫全失败）
- `unstable` —— 曾成功，但会挂起/崩溃，或不具备可构造的判据

> 「调用返回成功、几何量却不动」这一类（最危险，容易被误判成成功）统一收录在 [`SILENT_FAILURES.md`](SILENT_FAILURES.md)：逐项证据、共性教训、以及将来可用来复核的测试清单。

---

## broken（4 条）

### `sw_delete_face`

- 尝试：`IBody2.DeleteFaces3(faces, option, flag)`，`option ∈ {0,1,2,4,8}` × `flag ∈ {True,False}`
  = **10 组全试**
- 结果：全部返回 `(False, False)`，面数不变
- 另试：改用 `VARIANT(VT_ARRAY|VT_DISPATCH)` 传数组 —— 同样无效
- 结论：**不可用**。不要再换 option 组合去试。

### `sw_knit_surfaces`

- 尝试：穷举 `sldworks.tlb` 里含 `knit` 的成员
- 结果：只有 `IMirrorSolidFeatureData.KnitSurface`、`IPartingSurfaceFeatureData.Knit`
  —— 都是**别的特征的属性**，不是"缝合曲面"这个功能
- 注意：上游工具名是复数 `sw_knit_surfaces`，**没有**单数 `sw_knit_surface`
- 结论：**类型库无该 API**

### `sw_start_macro_recording` / `sw_stop_macro_recording`

- 尝试：穷举类型库里含 `record` / `macro` 的成员
- 结果：只有 `InsertMacroFeature*`（宏特征）、`IJournalManager.WriteJournalToMacro`、
  `RecordCOMCall` 等；**没有 Start/StopRecording**
- 结论：**类型库无该 API**。录制宏只能在 UI 里点。

---

## unstable（2 条，不进自动回归）

### `sw_add_sketch_dimension`

- `AddAlongXDimension` + `mark=1`：round 17 成功（0.01→0.03）
- 但 round 32 **挂起并崩溃过一次**
- 处置：保留实现，但调用方必须自己加超时保护；**不要放进无人值守批处理**

### `sw_show_all_planes`

- `UnblankRefGeom` 存在且可调用
- 但 `IFeature.Visible` 不反映图形区的实际可见性 → **构造不出"隐藏态"做 A/B**
- 处置：判据未立，不宣称已修

---

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

## unverified（31 条，已登记但没打通）

> 全部都有**实测依据**，按"卡在哪里"归类。每条的原始证据在
> `swkit.registry` 的 `note` 字段里，可用 `swkit registry` 查看。

### A. 参数列表未定（`DISP_E_PARAMNOTOPTIONAL` / 必填维）

| 工具 | 卡点 |
|---|---|
| `sw_revolve` | TLB 说 5 参、内核按 12 参调，**两边都报** `DISP_E_PARAMNOTOPTIONAL` |
| `sw_hole_wizard` | `HoleWizard5` 需 **27 个参数**，内核只传 14 个 |
| `sw_sketch_offset` | comtypes 要求 `CapEnds` 等必填维 |
| `sw_sketch_linear_pattern` / `sw_sketch_circular_pattern` | 要求 `XSpacingDim`/`RadiusDim` 等**尺寸对象**，不能只传数值 |
| `sw_sketch_convert_entities` | comtypes 下 `SketchUseEdge()` 不报错但**线段数不变** |
| `sw_sketch_extend` | 选中线段后调用，长度 **20→20 不变**（未知是否要选端点或标记） |

### B. 返回 `None` 或"假成功"（判据拦住了）

| 工具 | 卡点 |
|---|---|
| `sw_chamfer` | 特征数 +1 但**面数 6→6 不变** —— 典型假成功 |
| `sw_fillet` | 4 条边用 mark **0/1/2/4** 分别选中后仍返回 `None`（5 参/7 参都试过） |
| `sw_mirror` | 特征(2 个对象)+基准面(mark 32)都选好后仍返回 `None` |
| `sw_add_revision_table` | 空模板与真实 `.sldrevtbt` 都返回 `None`，`RevisionTable` 仍为 `None` |
| `sw_add_detail_view` | 返回 `None`、视图数不变：详图需父视图上**已有详图圆** |
| `sw_add_section_view` | 图纸里没有"前视基准面"（剖视要在视图上**画剖切线**，不是选基准面） |
| `sw_extruded_surface` | `FeatureExtruRefSurface(15 参)` 返回 `None`、曲面数 0；`IFeatureManager` 版 21 参语义未定 |

### C. 夹具/上下文造不出来（要更强的前置条件）

| 工具 | 卡点 |
|---|---|
| `sw_move_body` | 三种参数解释都无位移（包围盒 `dx=0`） |
| `sw_combine_bodies` | 两次相交拉伸被**自动合并**成 1 体，造不出"两个可组合的体" |
| `sw_split_body` | 需先有分割线/基准面，`PostSplitBody2` 5 参未尝试 |
| `sw_unfold` / `sw_fold` | 平板无折弯：特征 22→22、`GetBendState` 恒 1（需带折弯的钣金件） |
| `sw_edge_flange` / `sw_miter_flange` | 选边 + `SketchFeat=None` 仍返回 `None`；疑需法兰轮廓草图 |
| `sw_export_dxf` / `sw_export_iges` / `sw_export_flat_pattern` | 零件直接导无输出（DXF/IGES 需工程图或展开图上下文；IGES 调用不报错但**文件没生成**） |

### D. 枚举/接口在本机不存在

| 工具 | 卡点 |
|---|---|
| `sw_hide_all_planes` / `sw_hide_all_sketches` / `sw_show_all_sketches` | `swUserPreferenceToggle_e` 实测**只有 10 项**（`DisplayAxes`/`EntityPoints`/…），无基准面/草图开关 |

### E. 方程接口

| 工具 | 卡点 |
|---|---|
| `sw_add_equation` / `sw_delete_equation` | `IModelDoc2` **没有** `AddEquation`；`IEquationMgr` 需 comtypes（`sw_set_global_variable` 已用这条路打通，但**带尺寸名**的方程还没试成） |

### F. 破坏性/未跑通（本仓库主动不做）

| 工具 | 卡点 |
|---|---|
| `sw_dxp` | `autodim=True` 会**运行自动尺寸并保存文件** —— 破坏性，默认关闭 |
| `sw_flow_check` | 加载项自检与建工程可调，但**未跑通求解** |

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