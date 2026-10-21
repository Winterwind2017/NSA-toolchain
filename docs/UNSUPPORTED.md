# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

（暂无。真机试过失败的会记在这里，附失败证据。）

## pending（按依赖顺序）

| 能力 | 卡在哪 | 依赖 |
|---|---|---|
| `feature.chamfer` | `ChamferBuilder.SmartCollector` 的边选择怎么写还没验证 | 需要边选择（ScCollector） |
| `feature.hole` | `HolePackageBuilder` 参数多、需要点/面 | 依赖草图/点 |
| `feature.pattern` | `PatternFeatureBuilder.PatternService` 未摸清 | 依赖特征 + 方向 |
| `drawing.dimension` | 视图上的线性尺寸 API 未验证 | 依赖基础视图 |
| `cam.operation` | CAM 域需要 `cam_base`/`cam_advanced` 许可证 + 操作模板 | 许可证已具备，API 未挖 |
| `cae.mesh` | `NXOpen.CAE` 16 MB 绑定，起解算耗时长 | 许可证 `simulation` |
| `asm.constraints` | 装配约束 API 未挖 | 依赖组件 |
| `export.dxf` | `DxfdwgCreator` 需要图纸/视图上下文 | 依赖出图 |
| `sheet_metal.*` | 需要 `adv_sheet_metal_dsgn`（本机有） | 未开始 |

## external

（暂无。）
