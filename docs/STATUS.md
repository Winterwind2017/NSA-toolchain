# nxkit 现状（自动生成）

引擎：NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512`；内核：nxkit 0.1.0；技能：ww-nx-automation。

## 数字

- 真机通过能力：**102** 条（一次会话，连跑 2 次全绿）
- 其中带 L4（存盘→重开→复测）：**42** 条
- 未打通（有证据）：**18** 项
- 本机许可 feature：**4420** 个

## 按许可档位

| license | 能力数 |
|---|---:|
| assemblies | 7 |
| drafting | 10 |
| gateway | 26 |
| solid_modeling | 59 |

## 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 25 | 24 |
| sketch | 16 | 2 |
| attr | 10 | 1 |
| drawing | 10 | 0 |
| assembly | 7 | 1 |
| boolean | 6 | 6 |
| export | 6 | 0 |
| solid | 6 | 6 |
| curve | 5 | 0 |
| measure | 4 | 1 |
| file | 2 | 1 |
| inspect | 2 | 0 |
| part | 2 | 0 |
| surface | 1 | 0 |

## 未打通（按证据）

| 能力 | 卡在哪里 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `feature.chamfer` | `CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist` |
| `feature.hole` | `CreateHolePackageBuilder` 要 `HolePackage.Null` 哨兵，参数未摸清；**通孔已用「圆柱 + 布尔差」实现**（`feature.hole_cyl`） |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 |
| `measure.distance` | `MeasureDistance` 没有 `Distance` 属性，`Information()` 返回 `None`；数值在 `CreateFeature()` 产出的 `Measure` 表达式里，未打通 |
| `feature.mirror` | `MirrorFeatureBuilder.Plane` **只读**（只能 `PlaneOption` + `PlaneConstructor`），未找到可写入口 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 |
| `asm.constraints` | 只有 `ComponentAssembly.CreateConstraintGroupBuilder` / `Positioner`，约束对象没有创建入口 |
| `feature.rib` | `part.Features` 上**没有 `CreateRibBuilder`**（`CreateRpoBuilder` 倒是存在）；stub 里的 RibBuilder 类拿不到实例 |
| `feature.sweep` | `SweptBuilder.SectionList.Append`/`GuideList.Append` 都成功，`CommitFeature()` 报 `Unable to approximate guide string` |
| `feature.chamfer_angle` | `ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖 |
| `sketch.linear_dim` | `CreateDimension(HorizontalDim, dg1, dg2, origin, expr)` 报 `The first object associativity type is invalid`；`DimensionGeometry.AssocType` 的正确取值未找到 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸） |
| `export.parasolid` | 四种方式都失败：不选对象、`.Add(bodies)`、`.SetArray(bodies)`、`ExportFrom=DisplayedPart`，全部报 `Part has no valid export objects`（STL 用 `.Add` 已通） |
| `feature.thicken` | `FaceCollector.AddRules` 能过、`FirstOffset.SetFormula("5")` 返回 ok，但结果为 **2 个片体**（体积 0）；加上 `Tolerance` 后又变成单实体 **16,500,000 mm³**（100×50×3300），厚度语义不对 |
| `drawing.section_view` | 三条入口都不通：`part.SectionLines` 不存在；`CreateSectionViewBuilder` 需要 SectionLine/SectionView 对象；`CreateSectionInViewBuilder()` 只暴露 `Views`（SelectObjectList），不画剖切线时 `Co |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） |

## 为什么没到 200+

1. 每条都必须真机验证（改内核 → 跑 NX → 判据通过 → 连跑稳定），38 轮约 2.7 条/轮。
2. 可选 builder 家族大量不可脚本化：rib 无 CreateRibBuilder、CAM setup 全 None、剖视图拿不到 SectionLine、装配约束 CreateConstraint 缺失、DXF 导出死循环。
3. 同类变体不计入（Ø20→Ø30 不产生新知识）。
4. 判据质量优先（42/102 带 L4）。

## 怎么继续扩

- 新能力 append-only 追加到 `ACTIONS` 之前；先 py_compile + selftest，再真机 2 次。
- 判据只读 NX 状态；没打通写 `docs/UNSUPPORTED.md`（带错误原文）。
- 动手前 `nxkit licenses` 确认许可档位。
