# nxkit 最终交付报告

> 生成时间：2026-10-21（Asia/Shanghai）。数字由 `src/nxkit/caps.py` 现算，与 `docs/CAPABILITY_MATRIX.md` / `docs/STATUS.md` 同源。

## 1. 一句话结论

用真机跑通 **114 条** NX 2512 能力（其中 **52 条**做到存盘→重开→复测），做成可复现的内核 + 技能两个仓库；**没有**达到 200+ 的目标条数，原因在 §6 用数据说明。

## 2. 交付物

| 仓库 | 内容 | 位置 |
|---|---|---|
| `nxkit` | 内核：能力登记、动作库、判据、许可闸门、会话、CLI、文档 | `D:\bililive\nxkit` / GitHub `Winterwind2017/nxkit` |
| `ww-nx-automation` | 技能：SKILL.md、能力快照、校验/同步/安装脚本、4 个测试 | `D:\bililive\ww-nx-automation` / GitHub `Winterwind2017/ww-nx-automation` |
| 已安装 | `~/.dsh/skills/ww-nx-automation`、`~/.cursor/skills/ww-nx-automation` | 两处均 114 条，快照带 kernel commit |

## 3. 数字

- 真机通过：**114** 条
- 带 L4（存盘重开复测）：**52** 条（45%）
- 按族：

  - feature: 28（L4 28）
  - sketch: 17（L4 2）
  - drawing: 12（L4 0）
  - attr: 10（L4 2）
  - assembly: 8（L4 1）
  - boolean: 7（L4 7）
  - export: 7（L4 0）
  - solid: 7（L4 7）
  - curve: 6（L4 0）
  - measure: 5（L4 2）
  - file: 2（L4 1）
  - inspect: 2（L4 0）
  - part: 2（L4 1）
  - surface: 1（L4 1）

- 按许可档位：

  - assemblies: 8
  - drafting: 12
  - gateway: 28
  - solid_modeling: 66

## 4. 验证口径

见 `docs/VERIFY.md`：干净 clone → 9 离线测试 → `selftest` → `licenses` → 真机 114/114 → 技能校验 → 五处数字一致；连续 3 次全量无抖动（22 s 量级）。

## 5. 40 轮之后新增的能力（这一阶段的主要产出）

| 能力 | 关键发现 |
|---|---|
| `sketch.linear_dim` | `DimensionGeometry.AssocType` 要给 `Sketch.AssocType.StartPoint` |
| `asm.constraint_refs` | `CreateConstraintReference` 参数顺序与文档相反（先几何后组件） |
| `measure.distance` | 单位对象名 `MilliMeter`，数值在 `MeasureDistance.Value` |
| `feature.thicken` | 加厚会保留片体，判据只算 `IsSolidBody` |
| `export.parasolid` | 必须显式 `ObjectTypes.Solids = True` |
| `feature.mirror` | 镜像平面要传模型上的**面**，不是 `part.Planes` 造的 Plane |
| `solid.scale` | 缩放因子是 `UniformFactor`（不是 X/Y/Z 方向表达式） |
| `curve.helix` | `SizeLaw/PitchLaw` 的数值在 `.Value`（Expression）里 |
| `feature.spring` | 螺旋线可当管路径（曲线→实体链路打通） |
| `boolean.subtract_retain` | `Target` 要 Body；`RetainTool=True`+`RetainTarget=False` |
| `drawing.view_scale` | `Numerator/Denominator` 是相对自动缩放，判据要自校准 |
| `drawing.second_sheet` | 图纸 `Length` 是长边、`Height` 是短边 |

同期修掉一个**判据缺陷**：`judges._close` 原本对所有数值用 0.5 绝对容差，会把 0.59 判成 0.5；已改为按量级给容差（≥100→0.5、≥1→1e-3、<1→1e-6）。

## 6. 为什么没到 200+（数据）

| 事实 | 数据 |
|---|---|
| `FeatureCollection` 上的 builder 总数 | 223 |
| 已实际使用 | 19 |
| 逐个试过但卡住的接口 | 16 项（见 `docs/UNSUPPORTED.md`，带 NX 错误原文） |
| 失败类型 | 见下 |

失败类型分布：

1. **交互式 builder 在 journal 里缺上下文**（最多）：
   `HolePosition` 是 Section 但四种喂法全拒；`ParentViewBuilder.View` 不可写；
   `BooleanTool.FacePlaneTool.ToolPlane` 只认特定 Plane 句柄；
   `OffsetSurfaceBuilder.FaceSets` 要 `FaceSetOffset` 对象；
   `PatternBodyBuilder.ReferencePoint` 是服务 builder。
2. **求解器不可用**：`ComponentPositioner.EstablishNetwork()` 直接崩会话；
   `SolvePostponedConstraints()` 推不动 `NewlyCreated`。
3. **危险接口**：`CreateDxfdwgCreator().Commit()` 死循环（656 s CPU，需 taskkill）。
4. **构建器不存在**：`CreateRibBuilder` 不在 `FeatureCollection`；`TorusBuilder` 无；
   `CreateCamSetup` 四种模板全 None。

换句话说：**不是接口少，而是「脚本可用的接口」比「UI 可用的功能」少得多**；每条新能力平均要 2–4 次真机试错，而试错失败率约 40%。

## 7. 后续怎么扩（有依据的路线）

1. **曲线→实体链路**（已验证可复制）：螺旋→管成功，同理可做
   样条→管（线束）、曲线→旋转（回转体）、曲线→沿引导线扫掠。
2. **按「选择集三形态」逐个试**（`SelectObject`/`SelectObjectList`/`ScCollector`）：
   很多「失败」其实是选错了集合类型。
3. **优先幂等的几何能力**（有体积/面积判据），少碰交互式会话类。
4. **参考 NX 自带 journal 录制**：在 UI 里操作一次并录 journal，
   比盲猜 builder 参数快一个数量级（本阶段没做，是最大的效率缺口）。

## 8. 已知边界

- 只在 **NX 2512 + 本机许可** 上验证；跨版本未测。
- 判据是「读回值匹配」，不是「语义等价」；同一结果可能有别的实现。
- L4 只覆盖「存盘重开后读数不变」，不覆盖跨版本兼容。
- 制图/装配解算/孔包这三块基本没打开，是后续最大空白。
