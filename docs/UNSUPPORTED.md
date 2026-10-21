# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

（暂无。真机试过失败的会记在这里，附失败证据。）

## pending（按依赖顺序）

| 能力 | 卡在哪（真机证据） | 依赖 |
|---|---|---|
| `feature.chamfer` | `CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist` | 需要找到边选择的正确挂点（`SelectEdge`/selection intent） |
| `feature.hole` | `CreateHolePackageBuilder` 要 `HolePackage.Null` 哨兵，参数未摸清；**通孔已用「圆柱 + 布尔差」实现**（`feature.hole_cyl`） | 依赖点/面 |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 | 依赖基础视图（已通） |
| `measure.distance` | `MeasureDistance` 没有 `Distance` 属性，`Information()` 返回 `None`；数值在 `CreateFeature()` 产出的 `Measure` 表达式里，未打通 | 依赖 `Measure.CreateFeature` |
| `cam.setup` | `part.CreateCamSetup("mill_planar")` **返回 None**，随后 `part.CAMSetup` 报 `Current part does not contain valid setup`；试过 `mill_planar`/`mill_contour`/`drill` | 可能要在 CAM 应用上下文里建（`NXOpen.CAM` 域） |
| `feature.revolve` | `CreateRevolveBuilder` + `Section` + `Axes.CreateAxis` 后 `CommitFeature()` 报 **内存访问违例** | 需要换截面/轴构造方式 |
| `feature.mirror` | `MirrorFeatureBuilder.Plane` **只读**（只能 `PlaneOption` + `PlaneConstructor`），未找到可写入口 | 需要 PlaneConstructor 用法 |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints` | 只有 `ComponentAssembly.CreateConstraintGroupBuilder` / `Positioner`，约束对象没有创建入口 | 依赖组件（已通） |
| `sketch.constraints` | `CreateCoincidentConstraint(geom1, geom2)` 要 `Sketch.ConstraintGeometry` 对象，stub 里没有创建入口 | 未通 |
| `export.dxf` | `DxfdwgCreator` 需要图纸/视图上下文 | 依赖出图（已通） |
| `export.parasolid` | `ExportSelectionBlock.SetArray([body])` 后仍报 `Part has no valid export objects`（STL 用同样手法已通） | 需要 `ExportFrom`/`ObjectTypes` 的正确组合 |
| `drawing.projected_view` | `CreateProjectedViewBuilder(ProjectedView.Null)` 的 `Parent` 只读、`ParentView` 不存在 | 需要父视图的正确设入口 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |


## external

（暂无。）
