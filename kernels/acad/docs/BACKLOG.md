# 挖掘全量清单（backlog）

> 本文件由 `python tools/gen_backlog.py` 从 `docs/backlog.yaml` 生成。**不要手改**。
> 最近更新：2026-11-18

## 读法

这份文档回答一个问题：**要达到"理想效果"，一共还有多少东西能挖、要多少工时。**
它不是排期表——排期看 `docs/GAPS.md`（当前 8 周内要动的子集）。

| 文档 | 回答什么 |
|---|---|
| `CAPABILITIES.md` | 现在能做什么（62 条 verified） |
| **`BACKLOG.md`（本文）** | **还能挖什么、总量多少、哪些明确不做** |
| `GAPS.md` | 眼下先做哪几条、怎么绕 |
| `UNSUPPORTED.md` | 挖不动的原因与证据 |

## 理想效果（Definition of Done）

给定一张零件图/装配图/电气图的需求描述，agent 在真 AutoCAD 2025 上从零做到**可交付**：
标准图框 + 完整标注 + BOM + 打印样式，出 PDF/DWG 且重开一致；改图后重跑不变形；
能读别人的图（DXF/DWG 解析）；批量图纸一次出完；全程零静默失败（失败必须给出原因）。
判定方式：ALPHA_GATE 的 5 条工作流全过 **且** 2D 自动化面覆盖 ≥95%，
且每个"不能做"都有带证据的说明。


## 一、总量

| 门槛 | 项数 | 工时 | 占比 |
|---|---:|---:|---:|
| T1 必做 —— 缺了不能叫「能用」 | 11 | 178h | 27% |
| T2 应该做 —— 专业交付质量 | 32 | 320h | 48% |
| T3 可以做 —— 差异化 | 19 | 162h | 25% |
| **合计** | **62** | **660h** | 100% |

> 其中落在当前 `GAPS.md` 里的（眼下就要动的）：**5 条 / 70h**；也就是说 GAPS 只占全量的 **11%**——「先做哪几条」和「一共多少」是两个问题，不要混。

## 二、按域

| 域 | 已有能力 | 待挖项 | 待挖工时 | 为什么这个域重要 |
|---|---:|---:|---:|---|
| 标注与注释（`annotation`） | 22 | 9 | 74h | 机械图的语言；缺一条客户就发现"这图不专业" |
| 几何与编辑（`geometry`） | 8 | 5 | 74h | 只会画不会改，等于只能出一次图 |
| 块与外部引用（`block`） | 3 | 7 | 94h | 真实图纸 80% 的内容是块与外部引用 |
| 图层与特性（`layer`） | 4 | 5 | 28h | 出图质量与交接规范 |
| 布局与出图（`layout`） | 3 | 6 | 54h | 交付物就是这几张纸 |
| 三维与实体（`solid3d`） | 3 | 9 | 86h | 零件校核、干涉、投影出三视图 |
| 数据交换（`data`） | 3 | 5 | 60h | 与别人的图、BOM、工艺表对接 |
| 专业领域库（`domain`） | 4 | 5 | 78h | 电气/PLC/标准件——差异化的地方 |
| 工程化（`engine`） | 0 | 7 | 66h | 不稳、不可重复、没 CI，就等于不能交付 |
| Agent 接口（`agent`） | 0 | 4 | 46h | 让人/AI 真正能用的那一层 |

## 三、全量明细

排序：门槛（T1→T3）→ 影响分降序 → 工时升序。

### T1 必做 —— 缺了不能叫「能用」（11 项 / 178h）

| # | 能力 | 干什么 | 影响 | 工时 | 关键风险 / 说明 | 在 GAPS 里 |
|---|---|---|---:|---:|---|---|
| 1 | `dim.associative` | 关联标注（.NET 通道，改几何标注跟着变） | 5 | 16h | 插件通道已打通（dotnet/ + 安装目录 + LOADCTRLS=2）；需 DimAssoc + 几何关联表 | 是 |
| 2 | `mcp.tools` | MCP 工具面（67+ 条能力暴露成工具，附判据回传） | 5 | 16h | 与 ww-autocad-automation skill 的现有工具面对齐，避免两套 | — |
| 3 | `dxf.parse_full` | DXF 全量解析（实体/块/表/扩展数据），能读别人的图 | 5 | 24h | 现有 ezdxf/最小解析器只覆盖子集；"读别人的图"是承接旧项目的前提 | — |
| 4 | `geom.modify` | 编辑命令自动化（MOVE/COPY/ROTATE/SCALE/MIRROR/OFFSET/TRIM/EXTEND/FILLET/CHAMFER/ARRAY） | 5 | 40h | 必须按句柄选择 + 判据读几何量；命令行为主，少数靠 COM | — |
| 5 | `stability.watchdog` | 全局看门狗 + 自动恢复（COM 卡死/模态框/文档泄漏） | 4 | 10h | 已有 per-case 看门狗；缺"失败后自动重建会话继续跑" | — |
| 6 | `transaction.undo` | 能力级事务 + 失败回滚（UNDO 分组） | 4 | 12h | 一条能力失败不能污染整张图；现在靠"用完即关文档"规避 | — |
| 7 | `block.edit_inplace` | 块就地编辑（改一个定义，所有引用一起变） | 4 | 20h | BlockEditor 需 UI 模式；保底方案 = 重定义块 + 重插引用 + 属性迁移 | 是 |
| 8 | `block.dynamic` | 动态块参数与可见性（读 + 改） | 4 | 24h | 先做"读可见性状态"（覆盖多数看图场景），再做参数写入 | 是 |
| 9 | `ci.github` | CI 跑离线测试 + 文档新鲜度（真机用例跳过） | 3 | 6h | 现在靠人记得跑 tools/gen_*.py；PR 上没有门 | — |
| 10 | `plot.publish` | 批量出图（一套十几张一次出完） | 3 | 8h | -PUBLISH 会阻塞；走"逐布局出图 + 合并"的既有路径 | 是 |
| 11 | `interfere` | 干涉检查（布尔求交后看体积） | 2 | 2h | 替代方案已证可行；只需封装成能力 + 判据 | 是 |

### T2 应该做 —— 专业交付质量（32 项 / 320h）

| # | 能力 | 干什么 | 影响 | 工时 | 关键风险 / 说明 | 在 GAPS 里 |
|---|---|---|---:|---:|---|---|
| 1 | `plot.pagesetup` | 页面设置批量（图幅/比例/居中/打印样式） | 4 | 10h | 与 plot.style 同族，AcadLayout 可写项已探明 | — |
| 2 | `bom.link` | BOM 与块属性联动（改属性 → BOM 自动更新） | 4 | 12h | 需要"重算 BOM"能力，而不是一次性画表 | — |
| 3 | `dim.style_full` | 标注样式全量（常用 25 个 DIM* 变量可写可读） | 4 | 12h | 客户图框带自己的箭头/文字样式；读写都要判据 | — |
| 4 | `frame.std` | 国标图框（GB/T 14689 A0–A4 横竖 + GB/T 10609.1 标题栏） | 4 | 12h | 纯几何 + 属性块；关键是尺寸表要准 | — |
| 5 | `geom.param_rebuild` | 参数驱动重建（参数表 → 重画全套） | 4 | 12h | 几何约束不可用时的替代路线（完整版 AutoCAD 也没有） | — |
| 6 | `mech.bom_from_drawing` | 从图纸自动生成 BOM（块计数 + 属性汇总） | 4 | 12h | 与 block.count_extract、bom.link 有重叠，可合并实现 | — |
| 7 | `elec.wire_numbers` | 线号自动编号 + 交叉引用 | 4 | 16h | P&ID/电气图的核心；编号规则可配置 | — |
| 8 | `dim.style_presets` | 图纸规范预设（GB/ISO 标注样式一键套） | 3 | 6h | 纯 Python 数据 + 建样式；风险低 | — |
| 9 | `dwg.version` | 多版本 DWG 保存/降版（2013/2018/2025） | 3 | 6h | SaveAs 带版本码；判据看文件头 AC10xx | — |
| 10 | `geom.region` | 面域/边界（BOUNDARY / REGION） | 3 | 6h | 面域是 3D 操作的前置（拉伸/旋转都要闭合轮廓） | — |
| 11 | `solid.massprop` | 质量属性（体积/重心/惯性矩） | 3 | 6h | 读回即可判；校核场景必需 | — |
| 12 | `block.count_extract` | 块计数与属性导出（DATAEXTRACTION 替代） | 3 | 8h | 遍历 ModelSpace + 块表；大图性能要测 | — |
| 13 | `cli.run` | CLI 子命令（acadkit run <cap> --params） | 3 | 8h | 已有 caps.build 雏形 | — |
| 14 | `dim.leader` | 引线标注（多段引线 + 文字 + 箭头） | 3 | 8h | MLeader.TextString 赋值读回空串 → 用组装式（已有 balloon 经验） | — |
| 15 | `error.diagnostics` | 统一错误分类（忙/拒收/模态/权限）与可操作建议 | 3 | 8h | 现在靠人读 traceback；要变成结构化诊断 | — |
| 16 | `geom.offset` | 多段线偏移（含 bulge 圆弧） | 3 | 8h | bulge 处理是坑；先只做直线段偏移并明说限制 | — |
| 17 | `prop.bulk_set` | 批量改实体特性（层/颜色/线宽/线型） | 3 | 8h | 与 layer.set_current 配合；要能按选择集过滤 | — |
| 18 | `block.attribute_sync` | 属性批量同步/改写（ATTSYNC/BATTMAN 替代） | 3 | 10h | 重定义块 + 逐引用改属性；属性顺序要保 | — |
| 19 | `block.library` | 标准件/图框库（表驱动批量插块 + 属性） | 3 | 10h | 依赖 block.insert_with_attributes（已有） | — |
| 20 | `solid.fillet3d` | 3D 圆角/倒角 | 3 | 10h | 边选择要稳定 ID；失败率可能高，判据要能识别 | — |
| 21 | `table.csv_excel` | 表 ↔ CSV/Excel 双向 | 3 | 10h | BOM/明细表与人对接的实际形态 | — |
| 22 | `view.viewport` | 视口布置（比例/锁定/居中/多视口） | 3 | 10h | 图纸空间视口 API 部分可用，需探针确认锁定与比例 | — |
| 23 | `batch.plan` | 批量计划（JSON 多步 → 一次执行 + 汇总） | 3 | 12h | 与 alpha_gate 的工作流模型可复用 | — |
| 24 | `perf.batch` | 批量执行（一会话跑 N 个零件，省重复启动） | 3 | 12h | 每次启动 AutoCAD 约 15–20s；批量场景收益大 | — |
| 25 | `solid.loft` | 放样 | 3 | 12h | .NET 通道 CreateLoftedSolid；截面数与对应关系是坑 | — |
| 26 | `solid.sweep` | 扫掠（含对齐/扭曲） | 3 | 12h | .NET 通道 CreateSweptSolid；轮廓/路径要求闭合 | — |
| 27 | `xref.attach` | 外部引用（附着/绑定/重载/路径修复） | 3 | 12h | 相对路径与绑定是坑；判据看"引用数 + 解析状态" | — |
| 28 | `plc.io_table` | PLC I/O 表 ↔ 模块图 ↔ 地址联动 | 3 | 14h | 现有 plc.build 只画模块；缺地址映射 | — |
| 29 | `elec.symbols` | 电气符号库扩展（断路器/接触器/端子/线号） | 3 | 20h | 符号是程序化画，不需要外部资产 | — |
| 30 | `layer.filter` | 图层过滤器与批量开关（按前缀/颜色） | 2 | 6h | 出图前切层是高频动作 | — |
| 31 | `prop.match` | 特性匹配（MATCHPROP）自动化 | 2 | 6h | 命令行 + 源/目标选择 | — |
| 32 | `solid.shell` | 抽壳 | 2 | 6h | 薄壁件常用 | — |

### T3 可以做 —— 差异化（19 项 / 162h）

| # | 能力 | 干什么 | 影响 | 工时 | 关键风险 / 说明 | 在 GAPS 里 |
|---|---|---|---:|---:|---|---|
| 1 | `plot.precheck` | 出图前校验（空图/超界/线宽/字体缺失） | 3 | 8h | 交付前自检，能省客户退回 | — |
| 2 | `agent.recipes` | 面向 agent 的任务模板（零件图/装配图/BOM/出图） | 3 | 10h | 与 docs.recipe 复用 | — |
| 3 | `docs.recipe` | 配方库（每个常见图纸任务一条 recipe） | 3 | 10h | 现有 RECIPES.md 只有 3 条 | — |
| 4 | `projection.detail` | 剖视图/局部放大视图 | 3 | 14h | 现有投影只有 front/top/left | — |
| 5 | `mech.standard_parts` | 标准件库（螺栓/轴承/型材）图块 + 规格表 | 3 | 16h | 数据量大但机械；可先做 5 类常用 | — |
| 6 | `solid.assembly_align` | 装配对位（变换矩阵对齐，无约束 API） | 3 | 16h | 完整版无装配约束 API；靠矩阵算 | — |
| 7 | `linetype.load` | 线型加载与自定义线型 | 2 | 4h | 已有 centerline 用现成线型 | — |
| 8 | `symbol.datum` | 基准符号（A/B/C 基准目标） | 2 | 4h | 与 gdt.tolerance 配套 | — |
| 9 | `text.stack` | 堆叠文字（分数/上下标/公差） | 2 | 4h | MTEXT 的 \S 语法，判据要读回字面 | — |
| 10 | `plot.export_extra` | 出图格式扩展（SVG/PNG/DWF） | 2 | 6h | PDF/DWG/DXF 已够主流程 | — |
| 11 | `symbol.roughness_full` | 粗糙度完整（Ra/Rz/Rmax + 纹理方向 + 加工余量） | 2 | 6h | 现有 roughness 是 3 线 + Ra | — |
| 12 | `export.step` | 3D 导出 STEP/IGES | 2 | 8h | 走 ACAD 的 3D 输出；单位与精度要判 | — |
| 13 | `geom.hatch_full` | 填充完整（渐变/多段线边界/比例/关联） | 2 | 8h | 现有 hatch 只支持矩形边界 + ANSI31 | — |
| 14 | `packaging` | 打包与入口（pip 安装 / acadkit 命令） | 2 | 8h | 目前靠仓库内跑 | — |
| 15 | `solid.section_profile` | 剖切轮廓（SECTION 生成剖面几何） | 2 | 8h | 与三视图投影配套 | — |
| 16 | `text.field` | 字段（图框日期/图号自动更新） | 2 | 8h | FIELDEVAL 相关坑；可能只能"写死 + 重算" | — |
| 17 | `symbol.weld_full` | 焊接符号完整（GB/T 324 全字段） | 2 | 10h | 坡口/辅助符号/焊缝尺寸；字段多但纯画 | — |
| 18 | `xref.clip` | 外部引用裁剪（XCLIP） | 2 | 10h | 无 API，需探针；可能只能"按边界重画" | — |
| 19 | `layer.transparency` | 透明度 | 1 | 4h | 出图影响小 | — |


## 工时怎么读

* 单位是 **agent-hours**（本仓库现有实现速度下的估计），±50%，**用于比较与预算，不用于承诺**；
* 一条能力的实际成本 ≈ 实现 + 判据 + 踩坑，判据往往比实现贵；
* 结论：**660h 不是"再干 16 周"**，而是"按当前节奏约 4.1 个月的单人 agent 工作量"，
  其中 T1 部分（178h）才是"能不能用"的分水岭。

## 与 registry 的关系

清单里的 id 一旦落地，就应该出现在 `docs/registry.yaml` 里并标 `verified`；
反过来，`verified` 的能力**不应**再出现在本清单（测试会校验，防止虚报进度）。

## 明确不做

| 不做 | 为什么 |
|---|---|
| 交互式 UI / 动态输入 / 对象捕捉的交互行为 | 本仓库是 headless 自动化，不做人机界面 |
| 几何约束（GEOMCONSTRAINT / DIMCONSTRAINT / PARAMETRIC） | 完整版 AutoCAD 本身没有，属 Mechanical 专有能力 |
| 渲染 / 材质 / 动画 / 真实感出图 | 与"出工程图"无关 |
| Sheet Set Manager / 云协作 / 许可证管理 | 项目协同范畴，不属于单机出图 |
| 重写几何内核（复刻 AutoCAD） | 走驱动真机路线；内核由 AutoCAD 提供，这是本仓库的根本取舍 |
| 光栅图矢量化（Raster→Vector） | 需要专门算法与外部资产，另立项目更合适 |
