# 未打通项 × 现有能力 映射核对

目的：继续攻坚前先确认「未打通」的每一项是否其实已经有能力交付同一用户价值。
2026-10-22 核对 + 攻坚后：核对中翻案 3 项（见文末一节），当前剩余 7 项里 2 项部分覆盖、其余真缺。

| 未打通 | 判定 | 现有能力 | 说明 |
|---|---|---|---|
| `cam.setup` | 真缺 | — | 整族没有 CAM 能力；模块入口全 None |
| `cae.mesh` | 真缺 | — | NXOpen.CAE 无可用 builder |
| `sketch.constant_length` | 部分覆盖 | sketch.equal_length（两线等长） | 单曲线长度锁定 ≠ 两线等长 |
| `drawing.section_view` | 真缺 | base_view / projected_view 只覆盖普通视图 | 剖视图需要剖切线 + 父视图，两者都写不进去 |
| `solid.delete_body` | 部分覆盖 | solid.delete_face / solid.trim_body / boolean.subtract | 整删除一个体仍缺（两个 collector 都是 None） |
| `sketch.point_on_curve` | 真缺 | sketch.midpoint 等是别的约束 | 约束能建但几何不动（Sketch 无 Solve） |
| `sheet_metal.flange` | 真缺 | — | 整族没有钣金能力；SilhouetteFlange 方向参数被拒 |

## 核对中翻案并打通的

| 条目 | 真正的入口 | 结果 |
|---|---|---|
| `solid.move_body` | `CreateMoveBodyBuilder(MoveBody.Null)` + `Motion.Option=Distance` + `DistanceVector` + `DistanceValue` | 重心 50 → 150 ✅ |
| `feature.text` | `CreateCoordinateSystem(origin, Matrix3x3, is_temporary: bool)` | NXTEST → 6 条 Spline ✅ |
| `curve.intersection` / `curve.bridge` | 只读属性内部的 `SelectObject`/`ScCollector` 可写 | 均已打通 ✅ |

## 已移出的重复需求

| 原未打通条目 | 实际交付它的能力 | 依据 |
|---|---|---|
| `pattern.body_linear` | `feature.pattern_linear` | 同为 3 个阵列、体积 300000 |
| `feature.revolve_datum` | `feature.revolve` | 绕轴回转成体已通；只是不吃 `DatumAxis` |
| `feature.chamfer` / `feature.chamfer_angle` | 同名能力 | 早已验证，UNSUPPORTED 里是陈旧行 |

## 核对方法

```python
import sys; sys.path.insert(0, 'src')
from nxkit import caps
for c in caps.CAPS:
    print(c.id, c.family, c.title)
```

