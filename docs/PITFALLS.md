# 坑清单（NX 2512 实测）

> 每条都来自本机真机探针（`_nx_recon/probe_*.py`）。改代码前扫一遍。

## 一、builder 的 Null 哨兵各不相同

| 场景 | 正确写法 | 传错的表现 |
|---|---|---|
| 建块/圆柱/拉伸 | `part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)` | — |
| 布尔 | `CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)` | `TypeError: Expecting NXOpen.Features.BooleanFeature type, found Feature` |
| 基础视图 | `DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)` | `TypeError: Expecting NXOpen.Drawings.BaseView type` |

## 二、集合/属性没有想象中好用

| 现象 | 实测 | 用法 |
|---|---|---|
| `len(part.Bodies)` / `part.Bodies[0]` / `.ToArray()` | 全不支持（`BodyCollection` 只有 `FindObject`） | 从 `feature.GetBodies()` 拿 |
| 布尔后实体被"数了三次" | `Block(0)`、`Block(1)`、`Subtract(2)` 都指向同一个结果体 | 按 `b.Tag` 去重 |
| `part.PartUnits` | `int()` 抛错，`str()` 给 `'1'` | `str(...) in ("1","Millimeters")` |
| `part.ModelingViews.WorkView` | 插图纸后报 "The view is not a model view" | 遍历 `part.ModelingViews` 按名字取 |

## 三、拉伸/截面

- `CreateSectionsUsingCurves(curves, loop_option, chain_tol, dist_tol, angle_tol)`
  —— **5 个参数**，少一个报 `Function takes 5 arguments, 4 passed`。
- 带内孔截面用 `LoopOption.SeparateOuter`（`Separate` 会把内环当独立截面）。
- 拉伸距离：`Limits.StartExtend.SetValue(0.0)` / `EndExtend.SetValue(d)`；
  `StartExtend.Value` 是 `Expression`，**直接赋值 `Value` 会报只读**。
- `ExtrudeBuilder.Limits` 的实际类型是 `LinearLimits`，成员只有
  `StartExtend / EndExtend / SymmetricOption / Null / Tag / Validate`。

## 四、出图

- `InsertSheet(name, StandardSheetSize.A3, 1.0, 1.0, ProjectionAngleType.FirstAngle)`
  （枚举是 `FirstAngle`/`ThirdAngle`，**不是** `First`）。
- 基础视图必须给 `SelectModelView.SelectedView` 一个 `ModelView`
  （可选名：Top/Front/Right/Back/Bottom/Left/Isometric/Trimetric）。
- `ViewPlacementBuilder.Placement` 只读；不设位置就让它自动摆放。

## 五、导出

- 没有 `part.Export*`；导出走 `session.DexManager`：
  `CreateStepCreator()` / `CreateIgesCreator()` → 设 `OutputFile` → `Commit()`。
- 直接 `NXOpen.StepCreator()` 构造会 `Invalid self parameter passed`。

## 六、文件与进程

- `part.SaveAs(path)` 目标已存在 → `NXException: File already exists`，先删。
- 重开：`parts.OpenActiveDisplay(path, DisplayPartOption.AllowAdditional)`
  返回 **tuple**（`(BasePart, PartLoadStatus)`）。
- `run_journal` 即使全成功也可能返回 **退出码 1**；以 `result.json` 为准。
- `part.Close(CloseWholeTree.TrueValue, CloseModified.CloseModified, None)`。

## 七、许可证

- 反编译 `UF_MODL_create_block1` 看到每次调用都
  `JAM_start_uf_call` → `JAM_reserve_uf_license("solid_modeling")` → `UFX_*`。
  许可证不足时函数返回非 0、几何不动。
- 本机 `.dat` 有 **4,422 个 feature**（`solid_modeling`/`assemblies`/`drafting`/
  `cam_base`/`cam_advanced`/`sheet_metal`/`iges`/`dxf` 等都在）。
- `LicenseManager.CheckPresence("measure")` 返回 false **不代表**测量不可用
  （测量在 bundle 里，名字不是 "measure"）。判断可用性用实际调用。

## 八、Python 绑定是子集

- `ufs.Modl` 只有 213 个方法（原生 `UF_MODL_*` 815 个），`CreateBlock1` 不在里面。
- 建块/拉伸走 `NXOpen.Features`；UF 只在有绑定时用。
- `NXBIN\python` 里没有 `python.exe`，解释器嵌在 NX 里，只能 `run_journal -py`。

## 九、改代码时的自伤（2026-10-21 真踩）

- 用"从 `def X` 删到下一个 `def`"的方式删函数，**把夹在中间的 `ACTIONS` 字典一起删了**，
  于是 22 条能力全部 `KeyError`、整会话 0 通过；而 `selftest` 只检查
  `def X(` 是否存在，**照样通过**。
- 修法：`selftest` 与 `tests/test_offline.py` 现在同时检查
  `"动作": 函数,` 是否登记进 `ACTIONS`。删代码后先跑 `pytest` 再跑真机。
- `MeasureDistance` 没有 `.Distance`；`Information()` 返回 `None`。别对着它写判据。
- `MeasureManager.MeasureType` 的成员是 `Minimum`/`Maximum`，**不是** `MinimumDistance`。
- `part.CreateCamSetup("mill_planar")` 返回 `None` 且不建 setup（`CAMSetup` 报
  "Current part does not contain valid setup"）。

## 十、选择意图：chamfer / edge blend / pattern（2026-10-21 打通）

- **`SmartCollector` 是 None**：`CreateChamferBuilder(...)` 自带的 collector 读出来是 None，
  必须先自己建一个再**赋值**回去：
  ```python
  sc = part.ScCollectors.CreateCollector()
  rule = part.ScRuleFactory.CreateRuleEdgeDumb([edge])   # 不是 CreateRuleCurveDumb
  sc.AddRules([rule])                                     # ScCollector 没有 Add
  cb.SmartCollector = sc
  ```
- **圆角**：`CreateEdgeBlendBuilder(Feature.Null)` + `eb.AddChainset(sc, "5")` + `CommitFeature()`。
- **矩形阵列**：`pb.FeatureList.Add([feat])`；`rd = pb.PatternService.RectangularDefinition`；
  `rd.XDirection = part.Directions.CreateDirection(Point3d, Vector3d(1,0,0), UpdateOption.WithinModeling)`；
  `rd.XSpacing.NCopies.SetFormula("3")`、`rd.XSpacing.PitchDistance.SetFormula("120")`。
  `NCopies` 是 **Expression**（直接赋 int 报只读），默认 2 个实例。
- 三条都只动一个/一组具体边，判据看 **面数**（+1）与 **体积区间**。

## 十一、单边倒角的体积随"选中哪条边"变化

同一份 `chamfer_edge` 代码，体积可能读出 **99750 / 99375 / 98750** —— 因为
`body.GetEdges()` 的顺序不稳定，选中的边长度可能是 20/50/100 mm：
`V_removed = 0.5 × 5 × 5 × L`。判据必须给区间（本项目用 98500–100000），
不能写死一个数。同类问题也出现在 `chamfer_multi`（面数 10~12）。
