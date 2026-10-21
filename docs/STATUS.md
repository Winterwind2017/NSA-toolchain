# nxkit 现状（自动生成）

引擎：NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512`；内核：nxkit 0.1.0；技能：ww-nx-automation。

## 数字

- 真机通过能力：**112** 条（一次会话，连跑 2 次全绿）
- 其中带 L4（存盘→重开→复测）：**52** 条
- 未打通（有证据）：**15** 项
- 本机许可 feature：**4420** 个

## 按许可档位

| license | 能力数 |
|---|---:|
| assemblies | 8 |
| drafting | 10 |
| gateway | 28 |
| solid_modeling | 66 |

## 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 28 | 28 |
| sketch | 17 | 2 |
| attr | 10 | 2 |
| drawing | 10 | 0 |
| assembly | 8 | 1 |
| boolean | 7 | 7 |
| export | 7 | 0 |
| solid | 7 | 7 |
| curve | 6 | 0 |
| measure | 5 | 2 |
| file | 2 | 1 |
| inspect | 2 | 0 |
| part | 2 | 1 |
| surface | 1 | 1 |

## 未打通（按证据）

| 能力 | 卡在哪里 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `feature.hole` | `CreateHolePackageBuilder(HolePackage.Null)` 能建，`HoleType=Simple`、`GeneralSimpleHoleDiameter/Depth` 都能设；但 `HolePosition` 是个 `Section`，**所有 `AddToSection` 重载都拒绝* |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 |
| `feature.rib` | `part.Features` 上**没有 `CreateRibBuilder`**（`CreateRpoBuilder` 倒是存在）；stub 里的 RibBuilder 类拿不到实例 |
| `feature.sweep` | `SweptBuilder.SectionList.Append`/`GuideList.Append` 都成功，`CommitFeature()` 报 `Unable to approximate guide string` |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Co |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） |
| `feature.hole` | `CreateHolePackageBuilder(HolePackage.Null)` 能建，`HoleType=Simple`、`GeneralSimpleHoleDiameter/Depth` 都能设；但 `HolePosition` 是个 `Section`，**所有 `AddToSection` 重载都拒绝* |
| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能建，成员有 `BodyToDelete`/`BodyToKeep`，但两者**运行时都是 None**（`'NoneType' object has no attribute 'Add'`），`CommitFeature()` 报  |
| `solid.split_body` | 走到 `BooleanTool.FacePlaneTool.ToolPlane`：该属性**只要 `NXOpen.Plane`**，给 `DatumPlane` 报 `Expecting NXOpen.Plane type, found NXOpen.DatumPlane`；而 `part.Planes.CreateF |
| `solid.move_body` | `CreateMoveBodyBuilder(NXOpen.Features.MoveBody.Null)` 能建；`BodyToMove` 是 `ScCollector`（要 `AddRules(CreateRuleBodyDumb([body]))`）；`Motion` 是 `ModlMotion`，`DeltaX |

## 怎么继续扩

- 新能力 append-only 追加到 `ACTIONS` 之前；先 py_compile + selftest，再真机 2 次。
- 判据只读 NX 状态；没打通写 `docs/UNSUPPORTED.md`（带错误原文）。
- 未用 builder 仍有 200 个左右，但不少需要交互上下文（见 UNSUPPORTED）。
