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
