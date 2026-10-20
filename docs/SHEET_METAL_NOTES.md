# 钣金特征族：为什么"特征建出来了却没有几何"

> 结论基于 SW 2025 SP4.1（33.4.1）实测，2026-10-21。
> 涉及：`sw_edge_flange`、`sw_jog`、`sw_sketched_bend`、`sw_miter_flange`、unfold/fold。

## 一、现象

边法兰调用链能走完，**特征树里也确实出现 `EdgeFlange`**，但几何完全不动：

| 指标 | 调用前 | 调用后 |
|---|---|---|
| 体积 | 4800.0 mm³ | **4800.0 mm³** |
| 面数 | 6 | **6** |
| 边数 | 12 | **12** |
| 实体/曲面 | 1 / 0 | **1 / 0** |

这是典型的"假成功"：只看"特征 +1"会误判为成功。

## 二、根因（逐层排除后剩下的那条）

1. **轮廓草图是空的**
   `InsertSketchForEdgeFlange(edge, angle, flip)` 返回草图特征（如「草图8」），
   但用 `GetSpecificFeature2()` 取到 `ISketch` 后：
   `GetSketchSegments()` = **0**、`GetSketchPoints()` = **0**。

2. **法兰长度只能来自那条草图**
   `IEdgeFlangeFeatureData` 的全部成员里**没有 Length**：
   `BendAngle / BendRadius / OffsetType / OffsetDistance / PositionType /
   Relief* / GapDistance / Edges…` —— 长度由轮廓草图决定。
   草图空 → 长度为 0 → 零几何。

3. **不是展开状态导致的**
   `SetBendState(0/1/2/3)` + `EditRebuild3` 之后体积仍是 4800.0，
   面数/边数都不变；`FlatPattern` 特征的存在与否不影响结论。

4. **特征数据本身是"合法"的**
   `GetEdgeCount = 1`、`BendAngle = π/2`、`BendRadius = 2mm`、
   `OffsetType = 1`、`OffsetDistance = 4mm` —— 数据看着对，几何为零。

5. **想改数据会炸**
   对 `OffsetType` 赋值（0/1/2）抛
   `(-2147417851, '服务器出现意外情况')`（RPC_E_SERVERFAULT），
   说明该特征对象处于不完整状态。

6. **补轮廓线也没救回来**
   用 `EditSketch()` 进入草图、`CreateLine` 补一条 20mm 线、退出后再建法兰：
   仍然 4800.0。补线方向/坐标系未能与法兰轮廓平面一致
   （`+Y`/`-Y` 能建出 `EdgeFlange` 特征，`+X` 连特征都不建）。

## 三、参数层面的坑（就算将来能出几何也用得上）

| 参数 | 要求 |
|---|---|
| `InsertSheetMetalEdgeFlange` 第 2 参 `SketchFeat` | 必须传**草图特征对象**，传名字报"类型不匹配" |
| 可选 `IDispatch` 参数 | 必须传 `none_dispatch()`；传 Python `None` 报"类型不匹配" |
| `InsertSheetMetalEdgeFlange2` | 前两参要 `VARIANT(VT_ARRAY\|VT_DISPATCH, [...])` 数组；末参仍要 `none_dispatch()` |
| 选边 | 用 `IEdge.Select2(False, mark)` 可靠；按坐标 `SelectByID2("", "EDGE", x,y,z, …)` 在本夹具上全部失败 |

## 四、给未来的自己

* 这套 API **能建特征壳、不能建几何**，不要用"特征数 +1"当成功判据；
* 若哪天 SW 版本修好了 `InsertSketchForEdgeFlange` 让它生成**非空**草图，
  本文第二节第 1 条会失效——届时 `tests/` 里应加一条"草图线段数 > 0"的断言来提醒；
* 真正可交付的钣金能力目前只有：
  `sw_base_flange`（基体法兰）、`sw_insert_bends`（实体转钣金，能出
  `SheetMetal + ProcessBends + FlatPattern`）、`sw_hem`（卷边，特征+1）；
  `sw_flat_pattern_info` 可读展开信息。
