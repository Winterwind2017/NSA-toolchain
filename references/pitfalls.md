# 坑清单（NX 2512 实测）

> 每条都来自本机真机探针。改配方前扫一遍。

## 一、builder 的 Null 哨兵

| 场景 | 正确写法 | 传错的表现 |
|---|---|---|
| 块/圆柱/拉伸 | `Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)` | — |
| 布尔 | `CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)` | `TypeError: Expecting BooleanFeature` |
| 基础视图 | `DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)` | `TypeError: Expecting Drawings.BaseView` |

## 二、集合与属性

- `part.Bodies` 只有 `FindObject`：没有 `len()`、不能下标、没有 `ToArray()`。
  实体一律从 `feature.GetBodies()` 拿。
- 布尔之后 `Block(0)`/`Block(1)`/`Subtract(2)` 都指向同一个结果体：
  **按 `b.Tag` 去重**，否则体积是三倍。
- `part.PartUnits` 不能 `int()`；`str()` 给 `'1'`。
- 插图纸后 `part.ModelingViews.WorkView` 报 "view is not a model view"：
  遍历 `part.ModelingViews` 按名字取（Top/Front/Right/…）。

## 三、拉伸

- `CreateSectionsUsingCurves(curves, loop_option, chain_tol, dist_tol, angle_tol)`
  —— **5 个参数**。
- 带内孔用 `LoopOption.SeparateOuter`（`Separate` 会把内环当独立截面）。
- 距离：`Limits.StartExtend.SetValue(0.0)` / `EndExtend.SetValue(d)`；
  `Limits` 实际类型 `LinearLimits`，成员只有 `StartExtend/EndExtend/SymmetricOption`。
- `StartExtend.Value` 是 `Expression`，直接赋值报只读。

## 四、制图

- `InsertSheet(name, StandardSheetSize.A3, 1.0, 1.0, ProjectionAngleType.FirstAngle)`。
- 基础视图：`SelectModelView.SelectedView = <ModelView>`；
  `ViewPlacementBuilder.Placement` 只读，不设就自动摆放。
- `part.Dimensions` 存在，但创建签名与视图绑定还没打通（见 UNSUPPORTED）。

## 五、导出

- 入口在 `session.DexManager`：`CreateStepCreator()` / `CreateIgesCreator()`，
  设 `OutputFile` 后 `Commit()`。
- `NXOpen.StepCreator()` 直接构造 → `Invalid self parameter passed`。

## 六、文件与进程

- `SaveAs` 目标已存在 → `File already exists`，先删。
- 重开：`parts.OpenActiveDisplay(path, DisplayPartOption.AllowAdditional)` 返回 tuple。
- `run_journal` 全成功也可能退出码 1；以 `result.json` 为准。
- 一次会话约 15 s：**批量能力放一个 job**，别一条一起进程。

## 七、许可证

- 每个 UF 调用内部 `JAM_reserve_uf_license("<feature>")`（反编译证实）。
- `LicenseManager.CheckPresence("measure")` 返回 false **不代表**测量不可用。
- 本机 `.dat` 有 4,422 个 feature，`solid_modeling`/`assemblies`/`drafting`/`cam_base` 都在。

## 八、Python 绑定是子集

- `ufs.Modl` 只有 213 个方法（原生 815），`CreateBlock1` 不在。
- `NXBIN\python` 没有 `python.exe`，解释器嵌在 NX 里，只能 `run_journal -py`。
