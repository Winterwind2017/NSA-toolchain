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
| `feature.hole` | `CreateHolePackageBuilder(HolePackage.Null)` 能建，`HoleType=Simple`、`GeneralSimpleHoleDiameter/Depth` 都能设；但 `HolePosition` 是个 `Section`，**所有 `AddToSection` 重载都拒绝**点/面/列表（`No overload matches`），`CommitFeature()` 报 `Hole position not found. Specify a position.` | 需要点位 Section 的正确喂法 |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 | 依赖基础视图（已通） |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints`（解算） | 约束对象 + 两个面参考已能建（见能力 `asm.constraint_refs`），但 `GetConstraintStatus()` 仍是 `NewlyCreated(0)`，`SolvePostponedConstraints()` 也不推成 Solved；另外 `CreateConstraintReference(geometry, movable_object, uses_axis, is_indirect)` 的**参数顺序与文档相反**（先几何后组件） | 需要正确的求解触发方式 |
| `feature.rib` | `part.Features` 上**没有 `CreateRibBuilder`**（`CreateRpoBuilder` 倒是存在）；stub 里的 RibBuilder 类拿不到实例 | 需要别的筋入口 |
| `feature.sweep` | `SweptBuilder.SectionList.Append`/`GuideList.Append` 都成功，`CommitFeature()` 报 `Unable to approximate guide string` | 需要引导线/连续性或对齐参数 |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 | 需要别的枚举写入口 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） | 需要正确签名 |
| `sketch.constraints`（其余类型） | 重合/水平/竖直/等长/垂直/固定 已通；相切、中点、共线等未逐个验证 | 逐步加 |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Commit()` 返回 None | 需要"在视图上画剖切线"的取点接口 |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 | 需要父视图的正确设入口 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |


## external

（暂无。）

| `feature.hole` | `CreateHolePackageBuilder(HolePackage.Null)` 能建，`HoleType=Simple`、`GeneralSimpleHoleDiameter/Depth` 都能设；但 `HolePosition` 是个 `Section`，**所有 `AddToSection` 重载都拒绝**点/面/列表（`No overload matches`），`CommitFeature()` 报 `Hole position not found. Specify a position.` | 需要点位 Section 的正确喂法 |

| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能建，成员有 `BodyToDelete`/`BodyToKeep`，但两者**运行时都是 None**（`'NoneType' object has no attribute 'Add'`），`CommitFeature()` 报 `Missing target body` | 需要正确的选择集初始化方式 |

| `solid.split_body` | 走到 `BooleanTool.FacePlaneTool.ToolPlane`：该属性**只要 `NXOpen.Plane`**，给 `DatumPlane` 报 `Expecting NXOpen.Plane type, found NXOpen.DatumPlane`；而 `part.Planes.CreateFixedPlane(...)` 给的 Plane 虽能赋值，`Commit` 仍报 `The tool object is missing`；`DatumPlane` 又没有 `.Plane` 可取（只有 Feature/Origin/Normal） | 需要 NX 认的 Plane 句柄 |
