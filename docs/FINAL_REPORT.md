# nxkit 最终交付报告

> 数字由 `src/nxkit/caps.py` 现算，与 `docs/CAPABILITY_MATRIX.md` / `docs/STATUS.md` / `docs/registry.yaml` / 技能快照同源（`tools/check_consistency.py` 校验）。

## 1. 一句话结论

用真机跑通 **130 条** NX 2512 能力（其中 **54 条**做到存盘→重开→复测），做成可复现的内核 + 技能两个仓库；**没有**达到 200+ 的条数目标，原因在 §6 用数据说明，路线在 §7。

## 2. 交付物

| 仓库 | 内容 |
|---|---|
| `nxkit` | 内核：能力登记、动作库、判据、许可闸门、会话、CLI、`tools/add_cap.py` |
| `ww-nx-automation` | 技能：SKILL.md、能力快照、校验/同步/安装脚本、4 个测试 |
| 已安装 | `~/.dsh/skills/ww-nx-automation` 与 `~/.cursor/skills/ww-nx-automation` |

## 3. 数字

- 真机通过：**130**
- L4（存盘→重开→复测）：**54**（41%）
- 未打通（有证据）：**18**

| family | 能力数 | 其中 L4 | 许可 |
|---|---:|---:|---|
| feature | 30 | 29 | solid_modeling |
| sketch | 18 | 2 | solid_modeling |
| drawing | 12 | 0 | drafting |
| attr | 10 | 2 | gateway |
| assembly | 8 | 1 | assemblies |
| curve | 8 | 0 | solid_modeling |
| solid | 8 | 8 | solid_modeling |
| boolean | 7 | 7 | solid_modeling |
| export | 7 | 0 | gateway |
| inspect | 6 | 0 | gateway |
| measure | 6 | 2 | gateway |
| part | 4 | 1 | gateway |
| surface | 4 | 1 | solid_modeling |
| file | 2 | 1 | gateway |

按许可档位：

- `assemblies`：8 条
- `drafting`：12 条
- `gateway`：35 条
- `solid_modeling`：75 条

## 4. 验证口径

见 `docs/VERIFY.md`：干净 clone → 9 离线测试 → `selftest` → `licenses` → 真机 130/130（约 19 s）→ 技能校验 → 五处数字一致。

## 5. 这一阶段（61→79 轮）的主要产出

| 能力 | 关键发现 |
|---|---|
| `feature.chamfer_angle` | `ChamferBuilderChamferOption.OffsetAndAngle` + `AngleExp` 同时生效 |
| `feature.sweep` | 真正卡点是 **G0/G1 容差默认 0**；还要 `Swept.Null` 哨兵 + `Append(Section)` |
| `sketch.normal` | `CreateNormalConstraint(geom, help, geom, help)`；同族 slope/constant_angle 被 NX 拒 |
| `solid.split_body` | 工具体走 `BooleanTool.FacePlaneTool.ToolFaces.FaceCollector`（借辅助体的面） |
| `datum.plane` / `datum.axis` | `CreateFixedDatumPlane(origin, matrix)` / `CreateFixedDatumAxis(start, end)` |
| `curve.offset` | `CurvesToOffset` 是 Section；直线偏置必须给 `PointOnOffsetPlane`（`NXOpen.Point`） |
| `surface.ruled` | `FirstSection/SecondSection` 要直接 `AddToSection`（赋新 Section 对象无效） |
| `curve.project` | `PlaneToProjectTo` 只认 `NXOpen.Plane`（DatumPlane 反被拒） |
| `surface.through_curves` | `SectionsList.Append(section)` |
| `surface.sew` | `TargetBodies/ToolBodies` 是 `SelectObjectList`；`SewBuilderTypes.Sheet` |
| `measure.perimeter` | `MeasureFaces` 同时给 Area 与 **Perimeter** |
| `inspect.face_types` | `Face.SolidFaceType` 的 `str()` 是数字，要用**相等比较**取名字 |
| `inspect.body_state` / `edge_count` | 块 12 边 6 面、圆柱 **2 边** 3 面（无 seam 边） |
| `inspect.face_area_list` | 逐面面积分布比「总量」更能发现合并/拆分错误 |

工具化：新增 `tools/add_cap.py`（锚点插入 + py_compile + selftest），因为历史上 5 次手工改 `ACTIONS` 附近区域把整段字典删掉、导致全会话 0 条。

判据缺陷修正：`judges._close` 早期对所有数值用 0.5 绝对容差（把 0.59 判成 0.5 通过），已改为按量级给容差（≥100→0.5、≥1→1e-3、<1→1e-6）。

## 6. 为什么没到 200+（数据 + 分类）

| 事实 | 数据 |
|---|---|
| `FeatureCollection` 上的 builder 总数 | 223 |
| 已实际使用 | 19 |
| 试过但没打通（带 NX 错误原文） | 18 |

没打通的分三类（这是本阶段最重要的结论）：

| 类型 | 特征 | 例子 |
|---|---|---|
| **A. 服务对象无工厂** | `new` 出来的对象立刻失效，或 builder 要 `XxxService`/`XxxData` | `FaceSetOffset`、`PatternReferencePointService`、孔的公差三元组 |
| **B. 选择入口不可写** | `StartObject`/`FirstFace` 等只读，且找不到 `Set*` | `curve.bridge`、`curve.intersection`、`drawing.projected_view` |
| **C. 求值器不生效** | 参数全设上、`Commit` 也成功，几何不动 | `solid.move_body`（ModlMotion） |

反过来，**能做成的**几乎都是「参数是几何值/表达式/枚举」的 builder；凡是需要内部服务对象或交互上下文的，journal 一律拿不到。

## 7. 后续怎么扩（有依据的路线）

1. **录 journal**：在 UI 里操作一次并录制，把 NX 自己生成的调用序列抄进 `actions.py`——这是本阶段最大的效率缺口（比盲猜 builder 参数快一个数量级）。
2. **读类优先**：`measure` / `inspect` 一次通过率远高于写类；读数能力还能反过来加强写类判据（面数+边数+体积三重断言）。
3. **曲线→实体链路**：螺旋→管、圆→扫掠已通，可复制到样条→管、曲线→旋转。
4. **按选择集三形态排查**：`SelectObject(.Value)` / `SelectObjectList(.Add([x]))` / `ScCollector(.AddRules([r]))`；很多「失败」其实是选错集合类型。

## 8. 已知边界

- 只在 NX 2512 + 本机许可上验证；跨版本未测。
- 判据是「读回值匹配」，不是「语义等价」。
- L4 只覆盖「存盘重开后读数不变」，不覆盖跨版本兼容。
- 制图标注、装配解算、孔包这三块基本没打开，是最大空白。
