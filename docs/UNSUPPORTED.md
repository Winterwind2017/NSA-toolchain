# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

| 能力 | 真机证据 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `export.dxf` / `export.dwg` | **危险**：`CreateDxfdwgCreator().Commit()` 在无图纸上下文时**死循环**（实测 656 s CPU 未结束，需 taskkill）。不要在 journal 里再试 |

## pending（按依赖顺序）

| 能力 | 卡在哪（真机证据） | 依赖 |
|---|---|---|
| `feature.chamfer` | `CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist` | 需要找到边选择的正确挂点（`SelectEdge`/selection intent） |
| `feature.hole` | `CreateHolePackageBuilder` 要 `HolePackage.Null` 哨兵，参数未摸清；**通孔已用「圆柱 + 布尔差」实现**（`feature.hole_cyl`） | 依赖点/面 |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 | 依赖基础视图（已通） |
| `measure.distance` | `MeasureDistance` 没有 `Distance` 属性，`Information()` 返回 `None`；数值在 `CreateFeature()` 产出的 `Measure` 表达式里，未打通 | 依赖 `Measure.CreateFeature` |
| `feature.mirror` | `MirrorFeatureBuilder.Plane` **只读**（只能 `PlaneOption` + `PlaneConstructor`），未找到可写入口 | 需要 PlaneConstructor 用法 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints`（解算） | 约束对象 + 两个面参考已能建（见能力 `asm.constraint_refs`），但 `GetConstraintStatus()` 仍是 `NewlyCreated(0)`，`SolvePostponedConstraints()` 也不推成 Solved；另外 `CreateConstraintReference(geometry, movable_object, uses_axis, is_indirect)` 的**参数顺序与文档相反**（先几何后组件） | 需要正确的求解触发方式 |
| `feature.rib` | `part.Features` 上**没有 `CreateRibBuilder`**（`CreateRpoBuilder` 倒是存在）；stub 里的 RibBuilder 类拿不到实例 | 需要别的筋入口 |
| `feature.sweep` | `SweptBuilder.SectionList.Append`/`GuideList.Append` 都成功，`CommitFeature()` 报 `Unable to approximate guide string` | 需要引导线/连续性或对齐参数 |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 | 需要别的枚举写入口 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） | 需要正确签名 |
| `sketch.constraints`（其余类型） | 重合/水平/竖直/等长/垂直/固定 已通；相切、中点、共线等未逐个验证 | 逐步加 |
| `export.parasolid` | 四种方式都失败：不选对象、`.Add(bodies)`、`.SetArray(bodies)`、`ExportFrom=DisplayedPart`，全部报 `Part has no valid export objects`（STL 用 `.Add` 已通） | 需要 `ObjectTypes` 正确取值 |
| `feature.thicken` | `FaceCollector.AddRules` 能过、`FirstOffset.SetFormula("5")` 返回 ok，但结果为 **2 个片体**（体积 0）；加上 `Tolerance` 后又变成单实体 **16,500,000 mm³**（100×50×3300），厚度语义不对 | 需要正确的 offset 表达方式 |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Commit()` 返回 None | 需要"在视图上画剖切线"的取点接口 |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 | 需要父视图的正确设入口 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |


## external

（暂无。）

| `feature.hole` | H olePackageBuilder 能建；`HolePosition` 是 Section，缺"孔位点"选择规则（ScRuleFactory 无 point 规则） | 需要点选择规则 |
