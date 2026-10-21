# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

（暂无。真机试过失败的会记在这里，附失败证据。）

## pending（按依赖顺序）

| 能力 | 卡在哪（真机证据） | 依赖 |
|---|---|---|
| `feature.chamfer` | `CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist` | 需要找到边选择的正确挂点（`SelectEdge`/selection intent） |
| `feature.hole` | `HolePackageBuilder` 参数多，需要点位/面 | 依赖草图或点 |
| `feature.pattern` | `PatternFeatureBuilder.PatternService` 未摸清 | 依赖特征 + 方向 |
| `drawing.dimension` | `part.Dimensions` 存在，但集合类不在 core stub 里，`CreateHorizontalDimension` 的签名与视图绑定方式未验证 | 依赖基础视图（已通） |
| `measure.distance` | `MeasureDistance` 没有 `Distance` 属性，`Information()` 返回 `None`；数值在 `CreateFeature()` 产出的 `Measure` 表达式里，未打通 | 依赖 `Measure.CreateFeature` |
| `cam.setup` | `part.CreateCamSetup("mill_planar")` **返回 None**，随后 `part.CAMSetup` 报 `Current part does not contain valid setup`；试过 `mill_planar`/`mill_contour`/`drill` | 可能要在 CAM 应用上下文里建（`NXOpen.CAM` 域） |
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints` | 装配约束 API 未挖 | 依赖组件（已通） |
| `export.dxf` | `DxfdwgCreator` 需要图纸/视图上下文 | 依赖出图（已通） |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |
| `sketch.*` | `part.Sketches` 只有曲线 builder，草图创建入口未摸清 | 未开始 |

## external

（暂无。）
