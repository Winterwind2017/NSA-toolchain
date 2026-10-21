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
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 | 依赖基础视图（已通） |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints`（解算） | 约束对象 + 两个面参考已能建（见能力 `asm.constraint_refs`），但 `GetConstraintStatus()` 仍是 `NewlyCreated(0)`，`SolvePostponedConstraints()` 也不推成 Solved；另外 `CreateConstraintReference(geometry, movable_object, uses_axis, is_indirect)` 的**参数顺序与文档相反**（先几何后组件） | 需要正确的求解触发方式 |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 | 需要别的枚举写入口 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） | 需要正确签名 |
| `sketch.constraints`（其余类型） | 重合/水平/竖直/等长/垂直/固定 已通；相切、中点、共线等未逐个验证 | 逐步加 |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Commit()` 返回 None | 需要"在视图上画剖切线"的取点接口 |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 | 需要父视图的正确设入口 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |


## external

（暂无。）


| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能建，成员有 `BodyToDelete`/`BodyToKeep`，但两者**运行时都是 None**（`'NoneType' object has no attribute 'Add'`），`CommitFeature()` 报 `Missing target body` | 需要正确的选择集初始化方式 |


| `solid.move_body` | 拆到最里层：`BodyToMove.AddRules` 生效、`Motion.Option = ModlMotionOptions.DeltaXyz` 生效、`DeltaX/Y/Z` 是 float 且赋值成功（100/0/0）、`ManipulatorOrigin` 也能设；`Commit()` 与 `CommitFeature()` **都返回成功**，但**几何完全不动**（质心仍 50），早期还报过 `Feature has zero parameters`。判断：这条特征在 journal 下是空操作 | 需要 UI 上下文 |

| `pattern.body_linear` | `CreatePatternBodyBuilder(PatternBody.Null)` 能建，`SelectBody.Value = body` 也接受；但 `ReferencePoint` 是 `PatternReferencePointServiceBuilder`（不是选择集），不设它 Commit 报 `Incorrect object for this operation` | 需要正确的参考点服务配置 |

| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10） | 需要正确的求解触发方式 |

| `sketch.slope` / `sketch.constant_angle` / `sketch.constant_length` | 三个 API 都能调，但一律返回 `Unable to create sketch geometric constraint.`（同族的 normal / tangent / parallel 都能建）→ 这几个类型可能在 journal 下不可用 | 需要 UI 上下文或前置条件 |

| `feature.revolve_datum` | `RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立** | 用 `part.Axes.CreateAxis(point, dir)` 即可 |

| `curve.intersection` | `IntersectionCurveBuilder` 的 `FirstFace/SecondFace` **不可写**；`FirstSet/SecondSet` 是 `SelectObjectList`，`.Add([face])` 与 `.Add([body])` 都接受，但 `CommitFeature()` 一律报 `No objects for intersection curve`（两个片体确实存在，sheets=2） | 需要正确的对象输入方式 |


| `curve.bridge` | `BridgeCurveBuilder.StartObject/EndObject` **不可写**，直接 `CommitFeature()` 报 `Cannot create bridge.`（与 curve.intersection 同类） | 需要选择对象的正确入口 |
