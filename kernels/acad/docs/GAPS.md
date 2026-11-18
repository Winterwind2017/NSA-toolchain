# 缺口账本（gaps）

> 本文件由 `python tools/gen_gaps.py` 从 `docs/registry.yaml` + `docs/gaps_meta.yaml` 生成。
> **不要手改**：改 meta（影响分/工时/解锁条件），再重新生成。

三个文档的分工：

| 文档 | 回答的问题 |
|---|---|
| `CAPABILITIES.md` | 现在**能做**什么 |
| `UNSUPPORTED.md` | 用不了的**为什么**用不了（卡在哪一层、证据、复核条件） |
| **`GAPS.md`（本文）** | 还缺什么、**先做哪个**、要多少工时、**解锁需要什么** |

## 工时口径

`hours` 是 **agent-hours**（本仓库现有实现速度下的估计），不是人日。用来**排序和做预算**，
不用于对外承诺；±50% 的误差可接受。参照 CADCraft 的 calibration 思路
（每个选项/小修 0.3–0.7h，中等特性 2–5h，子系统 15–100h），但数字是本仓库自己的估计。

排序规则：**影响分降序 → 工时升序 → id 字典序**（同样重要时先做便宜的）。
`hours: 0` 表示"不再追"，旁边会标 **不做**。


## 一、全部缺口（按影响排序）

| # | 缺口 | 类型 | 影响 | 工时 | 受众 | 为什么排这儿 | 解锁条件 | 现在怎么办 |
|---|---|---|---|---:|---|---|---|---|
| 1 | `dim.associative` | dead | ●●●●● 5 | 16h | 机械、通用 | 机械图改尺寸后几何要跟着变；非关联标注在改图时是错的，客户一改就露 | 换路线 —— .NET 通道已打通（dotnet/，安装目录+注册表加载），在进程内实现 DimensionAssociation | 保持非关联 + 显式重建（acadkit 现做法，改一次几何要重标一遍） |
| 2 | `block.edit_inplace` | dead | ●●●●○ 4 | 20h | 机械、通用 | 图框/标准件都是块，客户要求"就地改一个块、所有引用一起变" | 换路线 —— .NET 通道已打通，实现插件里的 ACADKITEDITBLOCK（BlockEditor 需 UI 模式） | 重定义块 + 重新插入全部引用（acadkit 现做法，能出结果但丢属性） |
| 3 | `plot.publish` | planned | ●●●○○ 3 | 8h | 机械、电气 | 一套图十几张，逐张出图再合并很慢；PUBLISH 一次出全套 | 直接实现（-PUBLISH 会阻塞，需走逐布局出图+合并的既有路径） | export.pdf_multipage 逐布局出图后合并（已 verified） |
| 4 | `block.dynamic` | planned | ●●●○○ 3 | 24h | 机械、通用 | 客户端图纸里的动态块（可见性、拉伸参数）读不全，属性会丢 | 直接实现（需要解析动态块定义与参数，工作量大于普通块） | 只读可见性状态的静态几何，参数不可改 |
| 5 | `view.projection_builtin` | dead | ●●○○○ 2 | **不做** | 机械 | 三视图的出图路径；官方 SOLVIEW/SOLDRAW 本机不存在 | 不再追 —— 已用自建 CSG 投影替代，且投影质量可控 | projection.orthographic（自建 CSG 投影，已 verified） |
| 6 | `interfere` | dead | ●●○○○ 2 | 2h | 机械 | 装配干涉检查是设计校核的常规动作，但布尔求交已经能替代 | 直接实现（INTERSECT 后看体积 > 0，封装成一条能力） | 布尔求交看结果体积（acadkit 现做法，已验证） |
| 7 | `constraint.geometric` | dead | ●○○○○ 1 | **不做** | 机械、通用 | 完整版 AutoCAD 本身就没有几何约束，只有 Mechanical 有；不属于本仓库承诺范围 | 需要另装 AutoCAD Mechanical（AM 约束），本仓库不做 | 参数化在 Python 侧做"参数驱动重建"（acadkit 现做法） |

合计：**7 条**（dead 5 / planned 2），需要工时的 5 条共 **70h**。

## 二、dead：本机拿不到官方路径（墙）

这些不是「没时间做」，是「这条路走不通」。要么换路线（.NET 插件 / ObjectARX），要么承认不做。逐条卡点与证据见 `docs/UNSUPPORTED.md`。

- **`dim.associative`**（dim，影响 5/5）：机械图改尺寸后几何要跟着变；非关联标注在改图时是错的，客户一改就露
- **`block.edit_inplace`**（block，影响 4/5）：图框/标准件都是块，客户要求"就地改一个块、所有引用一起变"
- **`view.projection_builtin`**（view，影响 2/5）：三视图的出图路径；官方 SOLVIEW/SOLDRAW 本机不存在
- **`interfere`**（boolean，影响 2/5）：装配干涉检查是设计校核的常规动作，但布尔求交已经能替代
- **`constraint.geometric`**（constraint，影响 1/5）：完整版 AutoCAD 本身就没有几何约束，只有 Mechanical 有；不属于本仓库承诺范围

## 三、planned：能做但没做（账）

- **`plot.publish`**（—，影响 3/5，8h）：一套图十几张，逐张出图再合并很慢；PUBLISH 一次出全套
- **`block.dynamic`**（—，影响 3/5，24h）：客户端图纸里的动态块（可见性、拉伸参数）读不全，属性会丢


## 建议路线

1. **先做「换路线」能一次解锁的 4 条**：`dim.associative`、`block.edit_inplace`、
   `layer.state`、`solid.revolve` 全都卡在 ActiveX 够不着，而 **.NET 插件（进程内）**
   一条路能同时解决。插件骨架是一次性投入，之后每条约 4–8h。
2. **再做「直接实现」的低成本项**：`dim.update`(4h)、`interfere`(2h)、`plot.style`(12h)
   —— 不依赖新路线，做完立刻改善交付质量。
3. **`constraint.geometric` 不做**：完整版 AutoCAD 没有，属 Mechanical 专有，不在承诺范围。
4. **`view.projection_builtin` 不再追**：自建 CSG 投影已 verified，官方命令缺失不影响交付。

## 复核触发条件

跟 `UNSUPPORTED.md` 一致：换 AutoCAD 版本（R26+）/ 换机器 / Autodesk 更新 ActiveX 类型库时，
重新跑 `python tests/live_judges.py --only <族>`，确认哪些结论仍然成立。
**.NET 插件如果落地了，这几条 dead 要重测并改成 verified**——不要直接沿用本表的"不可用"。
