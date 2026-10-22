# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

| 能力 | 真机证据 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `DxfdwgCreator.Commit()`（旧路径） | journal 里**静默空操作**：不设 `SettingsFile` 时死循环；设了之后 `Commit()` 立刻返回但不写任何文件（连翻译器 log 都不产生）。已改用翻译器 CLI（`NXBIN` 下的 `dxfdwg.exe`） | 已替代 |

## pending（按依赖顺序）

| 能力 | 卡在哪（真机证据） | 依赖 |
|---|---|---|
| `feature.chamfer` | `CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist` | 需要找到边选择的正确挂点（`SelectEdge`/selection intent） |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints`（解算） | 已把整套流程走通：`Positioner.BeginAssemblyConstraints()` → `CreateConstraint(True)` → `ConstraintType=Touch` → 两个 `CreateConstraintReference`（成功，返回 `ConstraintReference`）→ `LoadConstraintGeometry` → `EndAssemblyConstraints()`（返回 None）→ `SolvePostponedConstraints()`（返回 None）。但**两面距离在解算前后都是 10.0**、`GetConstraintStatus()` 恒为 0 → 约束没解算 | 需要交互式约束求解器 |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 | 需要别的枚举写入口 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） | 需要正确签名 |
| `sketch.constraints`（其余类型） | 重合/水平/竖直/等长/垂直/固定 已通；相切、中点、共线等未逐个验证 | 逐步加 |
| `drawing.section_view` | `CreateSectionViewBuilder(base_view)` 报 `Invalid object type for this operation`；用 `SectionView.Null` 能构造，但 `ParentView` **不可写**、`Commit()` 报 `Null tag not allowed` | 需要剖切线先建（`SpecifySectionLineBuilder`）且父视图入口不可写 |


## external

（暂无。）


| `solid.delete_body` | `BodyToDelete` 构造出来是 `None`；赋一个 `ScCollector` 后 `CommitFeature()` 返回成功，但**体仍在**（`removed=0`）→ 空操作。删面（`solid.delete_face`）已打通，可作为替代 | 空操作 |


| `solid.move_body` | `ModlMotion` 参数全设上、两个 Commit 都成功但几何不动；`FreeTransformerBuilder`/`MeshTransformerBuilder` 只吃**面/曲线/点**，没有目标体入口（Commit 报 `Missing target body.`） | 需 UI 上下文 |

| `pattern.body_linear` | 7 轮尝试已到最深：`SelectBody.Value` **读回确认选上了**（`GetValue()` 返回 Body）、`PatternDefinition.PatternType=Linear` 可设、`XSpacing`（`DistancePatternSpacing`）的 `NCopies=3` / `PitchDistance=150` 可设、`XDirection` 给 Direction 可设、`XSelection.Value` 给边可设、`ReferencePoint.Point` 给 Point 也可设。结果只有两种：显式给 Point 时报 `Each patterned body must be face coincident with another patterned body.`，其余组合一律 `Incorrect object for this operation.` | 需要交互式阵列定义 |

| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10） | 需要正确的求解触发方式 |

| `sketch.slope` / `sketch.constant_angle` / `sketch.constant_length` | 三个 API 都能调，但一律返回 `Unable to create sketch geometric constraint.`（同族的 normal / tangent / parallel 都能建）→ 这几个类型可能在 journal 下不可用 | 需要 UI 上下文或前置条件 |

| `feature.revolve_datum` | `RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立** | 用 `part.Axes.CreateAxis(point, dir)` 即可 |




| `sheet_metal.flange` | `SilhouetteFlangeBuilder`：`BaseCurves`(Section) 与 `BaseFaces`(scCollector) 都能喂，`ReferenceVector` 也接受 Direction，但方向取 (0,0,1) 报 `Unable to project base curves to base faces.`，取 (0,1,0)/(1,0,0) 报 `Unable to create silhouette flange with given reference vector.` | 需要交互式选面/选向 |
| `feature.text` | `TextBuilder.TextString` 可设、`PlacementFaces` 可喂，但 `PlanarFrame.CoordinateSystem` 无入口：`CoordinateSystemCollection.CreateCoordinateSystem` 的参数签名对不上（`No overload matches these arguments`），Commit 恒报 `Reference coordinate system undefined.` | 需要 UI 里的坐标系 |
