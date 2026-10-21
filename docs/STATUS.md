# nxkit 现状（自动生成）

引擎：NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512`；内核：nxkit 0.1.0；技能：ww-nx-automation。

## 数字

- 真机通过能力：**136** 条（一次会话，连跑 2 次全绿）
- 其中带 L4（存盘→重开→复测）：**54** 条
- 未打通（有证据）：**14** 项

## 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 33 | 29 |
| sketch | 18 | 2 |
| drawing | 12 | 0 |
| attr | 10 | 2 |
| curve | 9 | 0 |
| solid | 9 | 8 |
| assembly | 8 | 1 |
| boolean | 7 | 7 |
| export | 7 | 0 |
| inspect | 6 | 0 |
| measure | 6 | 2 |
| surface | 5 | 1 |
| part | 4 | 1 |
| file | 2 | 1 |

## 未打通（按证据）

| 能力 | 卡在哪里 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Commit()` 返回 |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） |
| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能建，成员有 `BodyToDelete`/`BodyToKeep`，但两者**运行时都是 None**（`'NoneType' object has no attribute 'Add'`），`CommitFeature()` 报 `Missing t |
| `solid.move_body` | `ModlMotion` 参数全设上、两个 Commit 都成功但几何不动；`FreeTransformerBuilder`/`MeshTransformerBuilder` 只吃**面/曲线/点**，没有目标体入口（Commit 报 `Missing target body.`） |
| `pattern.body_linear` | `CreatePatternBodyBuilder(PatternBody.Null)` 能建，`SelectBody.Value = body` 也接受；但 `ReferencePoint` 是 `PatternReferencePointServiceBuilder`（不是选择集），不设它 Commit 报 `Incorrect ob |
| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10 |
| `feature.revolve_datum` | `RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立** |
| `curve.intersection` | `FirstFace/SecondFace` 只读，`FirstSet/SecondSet` 收对象但 Commit 报 `No objects for intersection curve`；用**组合投影**替代已打通（`curve.combined_projection`） |
| `curve.bridge` | `BridgeCurveBuilder.StartObject/EndObject` **不可写**，直接 `CommitFeature()` 报 `Cannot create bridge.`（与 curve.intersection 同类） |

## 新增能力的姿势

`python tools/add_cap.py spec.json`；批量试 API 用一次会话跑多组变体的探针（`_nx_recon/batch*.py`），比一次一个变体快 5–8 倍。
