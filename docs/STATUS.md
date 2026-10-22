# nxkit 现状（自动生成）

引擎：NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512`；内核：nxkit 0.1.0；技能：ww-nx-automation。

## 数字

- 真机通过能力：**144** 条（一次会话跑完，连跑 2 次全绿）
- 其中带 L4（存盘→重开→复测）：**54** 条
- 未打通（有证据）：**11** 项

## 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 33 | 29 |
| sketch | 18 | 2 |
| drawing | 14 | 0 |
| curve | 11 | 0 |
| attr | 10 | 2 |
| solid | 10 | 8 |
| export | 9 | 0 |
| assembly | 8 | 1 |
| boolean | 7 | 7 |
| inspect | 6 | 0 |
| measure | 6 | 2 |
| surface | 6 | 1 |
| part | 4 | 1 |
| file | 2 | 1 |

## 未打通（按证据）

| 能力 | 卡在哪里 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） |
| `drawing.section_view` | `CreateSectionViewBuilder(base_view)` 报 `Invalid object type for this operation`；用 `SectionView.Null` 能构造，但 `ParentView` **不可写**、`Commit()` 报 `Null tag not allowed` |
| `solid.delete_body` | `BodyToDelete` 构造出来是 `None`；赋一个 `ScCollector` 后 `CommitFeature()` 返回成功，但**体仍在**（`removed=0`）→ 空操作。删面（`solid.delete_face`）已打通，可作为替代 |
| `solid.move_body` | `ModlMotion` 参数全设上、两个 Commit 都成功但几何不动；`FreeTransformerBuilder`/`MeshTransformerBuilder` 只吃**面/曲线/点**，没有目标体入口（Commit 报 `Missing target body.`） |
| `pattern.body_linear` | 7 轮尝试已到最深：`SelectBody.Value` **读回确认选上了**（`GetValue()` 返回 Body）、`PatternDefinition.PatternType=Linear` 可设、`XSpacing`（`DistancePatternSpacing`）的 `NCopies=3` / `PitchDistance=150` 可设、 |
| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10） |
| `feature.revolve_datum` | `RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立** |
| `sheet_metal.flange` | `SilhouetteFlangeBuilder`：`BaseCurves`(Section) 与 `BaseFaces`(scCollector) 都能喂，`ReferenceVector` 也接受 Direction，但方向取 (0,0,1) 报 `Unable to project base curves to base faces.`，取 (0,1, |
| `feature.text` | `TextBuilder.TextString` 可设、`PlacementFaces` 可喂，但 `PlanarFrame.CoordinateSystem` 无入口：`CoordinateSystemCollection.CreateCoordinateSystem` 的参数签名对不上（`No overload matches these argumen |

## 新增能力的姿势

`python tools/add_cap.py spec.json`；批量试 API 用一次会话跑多组变体的探针（`_nx_recon/batch*.py`）。
