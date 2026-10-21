# nxkit 现状（自动生成）

引擎：NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512`；内核：nxkit 0.1.0；技能：ww-nx-automation。

## 数字

- 真机通过能力：**125** 条（一次会话，连跑 2 次全绿）
- 其中带 L4（存盘→重开→复测）：**54** 条
- 未打通（有证据）：**16** 项

## 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 30 | 29 |
| sketch | 18 | 2 |
| drawing | 12 | 0 |
| attr | 10 | 2 |
| assembly | 8 | 1 |
| curve | 8 | 0 |
| solid | 8 | 8 |
| boolean | 7 | 7 |
| export | 7 | 0 |
| measure | 5 | 2 |
| part | 4 | 1 |
| surface | 4 | 1 |
| file | 2 | 1 |
| inspect | 2 | 0 |

## 未打通（按证据）

| 能力 | 卡在哪里 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `feature.hole` | 依赖分析的"Section 吃曲线"成立：`HolePosition.AddToSection` **接受短线段**（不再报 No overload）；`BooleanOperation.SetTargetBodies([body])` 也被接受。但 `CommitFeature()` 最后卡在 **`The Tole |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 |
| `feature.rib` | `part.Features` 上**没有 `CreateRibBuilder`**（`CreateRpoBuilder` 倒是存在）；stub 里的 RibBuilder 类拿不到实例 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Co |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） |
| `feature.hole` | 依赖分析的"Section 吃曲线"成立：`HolePosition.AddToSection` **接受短线段**（不再报 No overload）；`BooleanOperation.SetTargetBodies([body])` 也被接受。但 `CommitFeature()` 最后卡在 **`The Tole |
| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能建，成员有 `BodyToDelete`/`BodyToKeep`，但两者**运行时都是 None**（`'NoneType' object has no attribute 'Add'`），`CommitFeature()` 报  |
| `solid.move_body` | 拆到最里层：`BodyToMove.AddRules` 生效、`Motion.Option = ModlMotionOptions.DeltaXyz` 生效、`DeltaX/Y/Z` 是 float 且赋值成功（100/0/0）、`ManipulatorOrigin` 也能设；`Commit()` 与 `CommitF |
| `pattern.body_linear` | `CreatePatternBodyBuilder(PatternBody.Null)` 能建，`SelectBody.Value = body` 也接受；但 `ReferencePoint` 是 `PatternReferencePointServiceBuilder`（不是选择集），不设它 Commit 报 `In |
| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动** |
| `feature.revolve_datum` | `RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立** |
| `curve.intersection` | `IntersectionCurveBuilder` 的 `FirstFace/SecondFace` **不可写**；`FirstSet/SecondSet` 是 `SelectObjectList`，`.Add([face])` 与 `.Add([body])` 都接受，但 `CommitFeature()` 一律 |

## 攻击顺序

见 `docs/DEPENDENCY.md`：A 级（前置齐全）→ B 级（缺一个可合成句柄）→ C 级（缺内部服务对象/交互上下文）→ D/X（不做）。

## 新增能力的正确姿势

`python tools/add_cap.py spec.json`（锚点插入 + py_compile + selftest）。不要手工删改 `ACTIONS` 附近区域——历史上 5 次把字典整段删掉。
