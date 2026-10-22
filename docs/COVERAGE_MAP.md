# 未打通项 × 现有能力 映射核对

目的：继续攻坚前先确认「未打通」的每一项是否**其实已经有能力交付同一用户价值**。
2026-10-22 核对结果：9 项里 2 项部分覆盖、7 项真缺；另移出 2 项重复需求。

| 未打通 | 判定 | 现有能力 | 说明 |
|---|---|---|---|
| `cam.setup` | 真缺 | — | 整族没有 CAM 能力；模块入口全 None |
| `cae.mesh` | 真缺 | — | NXOpen.CAE 无可用 builder |
| `sketch.constant_length` | 部分覆盖 | `sketch.equal_length`（两线等长） | 单曲线长度锁定 ≠ 两线等长 |
| `drawing.section_view` | 真缺 | `drawing.base_view` / `drawing.projected_view` 只覆盖普通视图 | 剖视图需要剖切线 + 父视图，两者都写不进去 |
| `solid.delete_body` | 部分覆盖 | `solid.delete_face`、`solid.trim_body`、`boolean.subtract` | 整删除一个体仍缺 |
| `solid.move_body` | 真缺 | `solid.scale` 只做缩放 | 没有平移或旋转体的可用入口 |
| `sketch.point_on_curve` | 真缺 | `sketch.midpoint` 等是别的约束 | 约束能建但几何不动（Sketch 无 Solve） |
| `sheet_metal.flange` | 真缺 | — | 整族没有钣金能力；SilhouetteFlange 方向参数被拒 |
| `feature.text` | 真缺 | `attr.string` 只是零件属性，不是三维文字 | TextBuilder 缺坐标系入口 |

## 已移出的重复需求

| 原未打通条目 | 实际交付它的能力 | 依据 |
|---|---|---|
| `pattern.body_linear` | `feature.pattern_linear` | 同为 3 个阵列、体积 300000；后者用 `PatternFeatureBuilder`，还带 L4 |
| `feature.revolve_datum` | `feature.revolve` | 绕轴回转成体已通（圆柱 37600–37800）；只是不能吃 `DatumAxis` 当轴 |
| `feature.chamfer` | `feature.chamfer` / `feature.chamfer_edge` | 这两条其实早已验证，是 UNSUPPORTED 里的**陈旧行**（已清理） |
| `feature.chamfer_angle` | `feature.chamfer_angle` | 同上，早已验证（已清理） |

## 核对方法

```python
import sys; sys.path.insert(0, 'src')
from nxkit import caps
for c in caps.CAPS:
    print(c.id, c.family, c.title)
```

判据：同一「用户价值」才算覆盖（例如「回转成体」算覆盖，「能把 DatumAxis 当轴」不算）。

