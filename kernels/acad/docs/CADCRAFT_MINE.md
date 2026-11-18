# 从 CADCraft 能挖什么（全量清单）

> 本文件由 `python tools/gen_cadcraft_mine.py` 从 `docs/cadcraft_mine.yaml` 生成。**不要手改**。
> 最近更新：2026-11-18

## 口径

上游：https://github.com/beclab/cadcraft（MIT OR Apache-2.0，12 crate，engine 133 个源文件 + 110 个测试文件）。

**许可证**：MIT OR Apache-2.0 —— 允许移植/改写/商用，但必须署名。
凡 `移植` 类条目落地时，都要往 `NOTICE.md` / `ATTRIBUTION.md` 加一条。

**这份清单回答的是**：把 CADCraft 的**优势**吸收进 nsa-toolchain，一共有多少东西、多少工时。
它**不是** AutoCAD 能力补全计划（那个在 `docs/BACKLOG.md`）——两者唯一重叠的是
`dxf` 解析与「真实语料/无损存盘」这类**方法**。

## 一个前提判断

CADCraft 的最大资产**不是**它的几何内核（那部分对我们无用，几何由 AutoCAD 提供），
而是三样东西：

1. **纯算法件**：LM 约束求解、曲线偏移/求交、填充边界探测——与 CAD 平台无关，可移植；
2. **行为规格**：110 个测试把 AutoCAD 的边界行为写成了可执行描述——免费的真机判据；
3. **数据模型**：关联标注、动态块夹点、阵列/快速标注的建模方式——AutoCAD 没有公开规格。


## 一、总量

| 吸收方式 | 项数 | 工时 | 占比 | 含义 |
|---|---:|---:|---:|---|
| 移植（改写成 Python） | 11 | 118h | 36% | 真改写成 Python 进 nsa-toolchain |
| 测试当规格 | 8 | 56h | 17% | 把它的测试翻译成我们的真机判据 |
| 读设计做参考 | 16 | 130h | 40% | 读模型/状态机，指导自己实现 |
| 只读了解 | 5 | 21h | 6% | 只为了解，不产出代码 |
| **合计** | **40** | **325h** | 100% | — |

**进度**：已完成 **22 / 40 项**（179h / 325h = 55%）。

## 二、按域

| 域 | 项数 | 工时 | 为什么值得挖 |
|---|---:|---:|---|
| 算法与几何（`algo`） | 10 | 100h | 我们的弱点在"算得准"（偏移/求交/圆角），这些是纯数学，可移植 |
| 文件格式（`format`） | 5 | 66h | 「读别人的图」与「存盘不丢数据」是我们的两个盲区 |
| 命令语义与数据模型（`command`） | 12 | 82h | AutoCAD 的行为细节（关联/夹点/阵列/快速标注）没有公开规格 |
| 测试当规格（110 个）（`spec`） | 5 | 38h | 每个测试都是一条 AutoCAD 行为的可执行描述，免费的真机判据 |
| 工具链与流程（`tooling`） | 5 | 19h | CI、日志、署名合规、parity 统计，成本低收益直接 |
| Agent 接口（`agent`） | 3 | 20h | 它的 MCP 工具 schema 与参数校验契约可直接对照 |

## 三、执行批次（按这个顺序做）

排序依据：先做**零风险且后续都要用**的（合规/CI），再做**不写实现就能产出判据**的（规格），
然后才是移植（算法→格式→模型）。批内按价值降序。

| 批次 | 主题 | 项数 | 工时 | 累计 |
|---|---|---:|---:|---:|
| 1 | 记分与合规 | 5 | 19h | 19h |
| 2 | 规格组（测试变判据） | 7 | 50h | 69h |
| 3 | 算法组（纯数学） | 10 | 100h | 169h |
| 4 | 格式组（读别人的图/不丢数据） | 5 | 66h | 235h |
| 5 | 模型组（AutoCAD 行为细节） | 11 | 74h | 309h |
| 6 | Agent 接口 | 2 | 16h | 325h |

**批次 1 · 记分与合规**（19h）：`cc.agents_md`、`cc.ci`、`cc.logging`、`cc.xtask_parity`、`cc.attribution`
**批次 2 · 规格组（测试变判据）**（50h）：`cc.spec.robustness`、`cc.mcp.params`、`cc.spec.files`、`cc.dimvars`、`cc.spec.annotation`、`cc.spec.draw_modify`（依赖 cc.dimvars）、`cc.spec.lisp`
**批次 3 · 算法组（纯数学）**（100h）：`cc.constraints.solver`、`cc.curves.offset`、`cc.constraints.expr`、`cc.constraints.infer`（依赖 cc.constraints.solver）、`cc.curves.fillet_chamfer`、`cc.geom.hatch_boundary`、`cc.geom.intersect`、`cc.curves.trim_extend`（依赖 cc.geom.intersect）、`cc.color.aci`、`cc.fonts.shx`
**批次 4 · 格式组（读别人的图/不丢数据）**（66h）：`cc.dxf.reader`、`cc.dwg.write_safety`（依赖 cc.dxf.reader）、`cc.dxf.writer`（依赖 cc.dxf.reader）、`cc.dwg.reader`、`cc.io.dispatch`
**批次 5 · 模型组（AutoCAD 行为细节）**（74h）：`cc.assoc.dim`、`cc.block.dyngrip`、`cc.array`、`cc.audit`、`cc.qdim`、`cc.block.refedit`（依赖 cc.assoc.dim）、`cc.compare`、`cc.plot.pipeline`、`cc.autosave`、`cc.overkill`、`cc.purge`
**批次 6 · Agent 接口**（16h）：`cc.mcp.tools`（依赖 cc.mcp.params）、`cc.control_server`

## 四、全量明细

排序：价值分降序 → 工时升序。`src` 是对应仓库路径（可直接去看）。

| # | 资产 | 能拿什么 | 方式 | 价值 | 工时 | 源路径 | 说明 |
|---|---|---|---|---:|---:|---|---|
| 1 | `cc.spec.robustness` | 畸形输入的鲁棒性规格（坏句柄/NaN/保存失败要报告） | 测试当规格 | 5 | 6h | crates/engine/tests（malformed_handles / non_finite_edits / save_reports_not_saved / props_bad_lineweight） | **我们完全没测过这一类**；这正是"零静默失败"的具体条目 |
| 2 | `cc.dxf.reader` | DXF 组码解析 + 未知实体保留（读别人的图） | 移植（改写成 Python） | 5 | 16h | crates/dxf | 直接替代"用 ezdxf 只读子集"；未知实体保留是承接旧项目的前提 |
| 3 | `cc.constraints.solver` | LM 约束求解器 + 自由度分析（可做"参数驱动重建"） | 移植（改写成 Python） | 5 | 24h | crates/constraints (lm.rs / residual.rs / dof.rs / model.rs) | 纯数值算法，与 Rust 无关；AutoCAD 完整版没有几何约束，这条能补上"改尺寸重算"的能力 |
| 4 | `cc.mcp.params` | JSON 参数校验与错误信息规格 | 测试当规格 | 4 | 4h | crates/engine/tests/json_param_validation.rs | agent 调用失败时"能不能看懂错误"决定可用性 |
| 5 | `cc.spec.files` | 文件读写与版本的行为规格 | 测试当规格 | 4 | 6h | crates/engine/tests（save_version / save_as_export / open_svg / lin_pat_files / save_reports_not_saved） | 与我们 export.lossless、dwg.version 直接对应 |
| 6 | `cc.dimvars` | DIM* 变量的语义表（哪些互相覆盖、哪些要 REGEN） | 测试当规格 | 4 | 8h | crates/engine/src/cmd/annotate* + tests/dim_vars.rs | 我们 env.dimstyle 只碰了 2 个变量；这张表能直接变成判据 |
| 7 | `cc.dwg.write_safety` | 保存不丢数据的差异报告机制 | 读设计做参考 | 4 | 8h | crates/dwg + docs/gaps.md（头号 blocker） | 它的 #1 blocker 反过来教我们：导出后要能证明"什么都没丢" |
| 8 | `cc.assoc.dim` | 关联标注的几何关联表（哪条边、哪个子实体、参数化距离） | 读设计做参考 | 4 | 10h | crates/engine/src/assoc.rs | 我们 dim.associative 卡在"不知道 AutoLISP/COM 怎么建关联"；它的数据模型能反推需要哪些字段 |
| 9 | `cc.block.dyngrip` | 动态块夹点与参数模型（可见性/拉伸/翻转） | 读设计做参考 | 4 | 10h | crates/engine/src/cmd/blocks/dyngrip.rs + tests/dynamic_block_data.rs | 我们的 block.dynamic 只做"读可见性"，它的模型能告诉我们还要读哪些 |
| 10 | `cc.curves.offset` | bulge 感知的多段线偏移 + 椭圆/样条偏移 + 自交清理 | 移植（改写成 Python） | 4 | 10h | crates/geom（offset 相关）+ engine/tests/offset_* | 我们 geom.offset 只有直线段；bulge 与自交是主要坑，它已有测试覆盖 |
| 11 | `cc.mcp.tools` | MCP 工具 schema 与错误契约（命令/检查/渲染三分） | 读设计做参考 | 4 | 10h | crates/mcp | 我们 backlog 有 mcp.tools；它的 schema 组织方式可直接对照 |
| 12 | `cc.spec.annotation` | 标注与文字的渲染/定位行为规格 | 测试当规格 | 4 | 10h | crates/engine/tests（dim_* / mleader_* / mtext_* / qdim* / dimtedit_prompts） | 我们对文字避让、标注间距只有零星经验，这里成体系 |
| 13 | `cc.spec.draw_modify` | 绘制与编辑的边界行为规格 | 测试当规格 | 4 | 12h | crates/engine/tests（modify_curves / fillet_chamfer / offset_* / pline_arc_xline_options / pedit_splinedit） | 每条都能翻译成一个 acadkit 判据（真机跑 + 读几何量） |
| 14 | `cc.dxf.writer` | DXF 回写（含未建模数据、句柄/扩展字典） | 移植（改写成 Python） | 4 | 14h | crates/dxf | 与 reader 配套；我们现在的 DXF 导出靠 AutoCAD，缺"离线改文件"能力 |
| 15 | `cc.agents_md` | agent 工作规则（分层、everything-is-a-command、never-crash） | 只读了解 | 3 | 3h | AGENTS.md（9.4KB）/ CLAUDE.md（8.1KB） | 低成本；对照我们 AGENTS.md 的缺口（例如"不许静默失败"的写法） |
| 16 | `cc.ci` | 打包 lint 与发布流水线 | 移植（改写成 Python） | 3 | 4h | .github/workflows（packaging-lint.yml / release.yml） | 我们 backlog 里有 ci.github；它的 workflow 可直接改写 |
| 17 | `cc.logging` | 结构化日志与诊断输出 | 读设计做参考 | 3 | 4h | apps/cadcraft/src/logging.rs（24KB） | 与我们 backlog 的 error.diagnostics 对应 |
| 18 | `cc.spec.lisp` | LISP 语料（哪些写法必须支持/必须拒绝） | 测试当规格 | 3 | 4h | crates/engine/tests/lisp_corpus.rs | 我们有 lisp.execute 但没有语料；它给了拒绝集 |
| 19 | `cc.array` | 阵列语义（矩形/极轴/路径 + 阵列编辑） | 读设计做参考 | 3 | 6h | crates/engine/src/cmd/array.rs + array/edit.rs | ARRAY 的选项组合坑多，读它的模型省试错 |
| 20 | `cc.audit` | AUDIT 的检查项清单（重复句柄/坏块/悬空引用） | 测试当规格 | 3 | 6h | crates/engine/src/audit.rs + cmd/audit.rs | 我们没有任何"图纸自检"能力，这个清单能直接变成 acadkit 的检查器 |
| 21 | `cc.constraints.expr` | 参数表达式求值（d1 = d2/2 + 5 这类） | 移植（改写成 Python） | 3 | 6h | crates/constraints/expr.rs | 求解器的前置；也可单独用于"参数表驱动" |
| 22 | `cc.control_server` | 外部控制协议（长驻进程 + 命令队列） | 读设计做参考 | 3 | 6h | apps/cadcraft/src/control_server.rs | 对应我们 backlog 的 perf.batch（避免每次启动 AutoCAD） |
| 23 | `cc.qdim` | 快速标注的判定（何时串成连续/基线/并列） | 读设计做参考 | 3 | 6h | crates/engine/src/cmd/annotate_qdim.rs + tests/qdim_modes.rs | 我们 dim.continuous/baseline 要手动给点；QDIM 能自动分组 |
| 24 | `cc.xtask_parity` | 源码扫描式覆盖统计 | 读设计做参考 | 3 | 6h | xtask（cargo xtask parity）+ docs/parity-checklist.md | 我们的 PARITY 是自评分母；它的"从源码扫命令"能减少自说自话 |
| 25 | `cc.block.refedit` | 就地编辑的状态机（REFEDIT/BEDIT 的进入-修改-保存原子性） | 读设计做参考 | 3 | 8h | crates/engine/src/cmd/blocks/refedit.rs + bedit.rs | 我们走"重定义块+重插"，但状态机值得对照 |
| 26 | `cc.compare` | 两张图的差异比对（新增/删除/改动） | 读设计做参考 | 3 | 8h | crates/engine/src/cmd/file/compare.rs + tests/compare.rs | 我们完全没有"图纸比对"；对"改图后重跑是否变形"的场景很有用 |
| 27 | `cc.constraints.infer` | 自动约束推断（从几何猜水平/相切/共线） | 读设计做参考 | 3 | 8h | crates/constraints/auto.rs | 没有它，用户要手动标注每条约束；可后置 |
| 28 | `cc.curves.fillet_chamfer` | 圆角/倒角的解析解（含不相切、退化半径） | 移植（改写成 Python） | 3 | 8h | crates/geom + engine/tests/fillet_chamfer.rs | 退化情形是判据来源，直接抄测试更快 |
| 29 | `cc.plot.pipeline` | 打印样式/透明度/多图纸的管线设计 | 读设计做参考 | 3 | 8h | crates/engine（plot_* 测试、plotters.rs） | 我们 plot.style 刚打通；它把"样式表→线宽→透明"分层的做法可对照 |
| 30 | `cc.geom.hatch_boundary` | 填充边界探测（射线法 + 孤岛嵌套） | 移植（改写成 Python） | 3 | 10h | crates/geom + engine/tests/hatch_assoc.rs | geom.hatch 目前只支持矩形边界 |
| 31 | `cc.geom.intersect` | 椭圆/样条与直线/圆的交点（解析 + 细分混合） | 移植（改写成 Python） | 3 | 10h | crates/geom | 我们的椭圆/样条相交目前靠 AutoCAD 命令，离线几何校验时要自己算 |
| 32 | `cc.curves.trim_extend` | 修剪/延伸的边界求交、最近点、多边界选择 | 移植（改写成 Python） | 3 | 12h | crates/geom + engine/tests/modify_curves.rs | 我们走 AutoCAD 命令，但"选哪条边/切哪一段"的判定逻辑仍要自己写 |
| 33 | `cc.dwg.reader` | DWG 位级读取（不启 AutoCAD 也能查图） | 读设计做参考 | 3 | 24h | crates/dwg | 我们已有 AutoCAD 可读 DWG；价值在"批量扫描不占许可证/不启窗口" |
| 34 | `cc.attribution` | 移植署名与合规做法 | 只读了解 | 2 | 2h | ATTRIBUTION.md / NOTICE | 一旦真 port 代码必须做；MIT/Apache 双许可的写法可直接照抄格式 |
| 35 | `cc.autosave` | 自动保存与崩溃恢复语义 | 只读了解 | 2 | 4h | crates/engine/src/autosave.rs + tests/autosave.rs | 我们靠"用完即关"，恢复策略可借鉴 |
| 36 | `cc.color.aci` | ACI 调色板 / 真彩 / 打印样式色映射表 | 移植（改写成 Python） | 2 | 4h | crates/color | 出图配色与 CTB 映射要查表，纯数据 |
| 37 | `cc.io.dispatch` | 格式探测与读写分派 | 只读了解 | 2 | 4h | crates/io | 结构参考，规模小 |
| 38 | `cc.overkill` | 重叠/重复对象删除的判定规则 | 读设计做参考 | 2 | 4h | crates/engine/tests/overkill.rs | 清理类能力我们没有；判定规则简单但边界多 |
| 39 | `cc.purge` | 未用对象清理（块/图层/样式）的依赖判定 | 读设计做参考 | 2 | 4h | crates/engine/src/cmd/blocks/purge.rs + tests/purge_* | 交付前瘦身常用 |
| 40 | `cc.fonts.shx` | SHX 字形解析（算文字宽度、避免文字重叠） | 只读了解 | 2 | 8h | crates/fonts | 只想知道它如何估字宽；完整移植性价比低 |

## 五、进度台账（每批做完就更新）

| 批次 | 主题 | 已完成 / 总项 | 完成工时 / 总工时 |
|---|---|---:|---:|
| 1 | 记分与合规 | 4 / 5 | 15h / 19h |
| 2 | 规格组（测试变判据） | 6 / 7 | 38h / 50h |
| 3 | 算法组（纯数学） | 9 / 10 | 92h / 100h |
| 4 | 格式组（读别人的图/不丢数据） | 3 / 5 | 34h / 66h |
| 5 | 模型组（AutoCAD 行为细节） | 0 / 11 | 0h / 74h |
| 6 | Agent 接口 | 0 / 2 | 0h / 16h |

已落地的条目与证据：

- `cc.agents_md` —— AGENTS.md §5/§6/§7（三条规则，注明上游来源）
- `cc.attribution` —— ATTRIBUTION.md + AGENTS §5–§7 + parity_scan
- `cc.ci` —— .github/workflows/ci.yml（离线门 + 生成物一致性 + parity 扫描）
- `cc.xtask_parity` —— tools/parity_scan.py（实现↔registry 一致 + 弹框命令扫描）
- `cc.dimvars` —— tests/live_robustness.py E 组（6 个 DIM* 变量读回一致 + 非法负字高被拒）
- `cc.mcp.params` —— tests/live_robustness.py F 组（坏参数/缺参必须抛明确异常，不得静默画出错东西）
- `cc.spec.annotation` —— tests/live_spec_annotation.py 8 例（文字高度/替代/位置/基线间距/MTEXT 宽度/长文本），8/8 通过
- `cc.spec.files` —— tests/live_spec_files.py F1–F6（版本/往返/DXF/坏扩展名/缺目录），6/6 通过；顺带修 save_as 静默失败
- `cc.spec.lisp` —— tests/live_robustness.py G 组（合法 LISP 能画、非法 LISP 报错不挂）
- `cc.spec.robustness` —— tests/live_robustness.py A/B/C/D 组（非有限、坏句柄、坏参数、保存失败），15/15 通过
- `cc.color.aci` —— src/acadkit/geom2d/colors.py（ACI↔RGB、灰度阶梯、rgb_to_aci 最近邻）
- `cc.constraints.expr` —— src/acadkit/solve/constraints.py::evaluate_expr（只允许四则与括号；拒任意代码，测试有用例）
- `cc.constraints.infer` —— src/acadkit/solve/infer.py（水平/垂直/重合/平行推断 + 置信度；低置信度默认不落地）；测试覆盖容差与误判
- `cc.constraints.solver` —— src/acadkit/solve/constraints.py（LM + 数值雅可比 + 秩算自由度）；tests/test_solver.py 8 例（收敛/欠约束/矩形/冲突必失败/垂直等长/定点/表达式）
- `cc.curves.fillet_chamfer` —— src/acadkit/geom2d/curves.py::fillet/chamfer（含半径过大、平行、越界必抛错）
- `cc.curves.offset` —— src/acadkit/geom2d/polygon.py::offset_polygon（miter + 外/内 + 自交/翻转/内接圆三重拦截）
- `cc.curves.trim_extend` —— src/acadkit/geom2d/trim.py（cut_params/trim_segment 三种保留侧/extend_segment 双向延长，含圆剪刀与无交点必抛错）；13 例测试
- `cc.geom.hatch_boundary` —— src/acadkit/geom2d/polygon.py（point_in_polygon/classify_islands/hatch_area 净面积）
- `cc.geom.intersect` —— src/acadkit/geom2d/curves.py（线线/线圆/圆圆/椭圆线）；tests/test_curves.py 覆盖相切/相离/越界
- `cc.dxf.reader` —— src/acadkit/dxf/document.py::read（组码对/SECTION 分段/实体索引/图层表/ACADVER；畸形必抛错）+ tests/test_dxf.py
- `cc.dxf.writer` —— src/acadkit/dxf/document.py::write/add_entity（逐对重放，未知实体原样保留；往返逐对比对一致）
- `cc.io.dispatch` —— src/acadkit/dxf/io.py::sniff（DWG/DXF/PDF/STEP/STL/PNG/ZIP 文件头探测 + 缺失文件报错）


## 怎么用这份清单

1. **先看总量**：325h / 40 项。其中「移植」11 项 118h，
   「测试当规格」8 项 56h —— 后者性价比最高（不用写实现，直接把测试变判据）。
2. **按价值挑**：价值 5 的两条是 `cc.constraints.solver`（参数驱动重建）与
   `cc.dxf.reader`（读别人的图）+ `cc.spec.robustness`（畸形输入）；
   这三条分别补的是「改图」「承接旧项目」「不静默失败」。
3. **不要整体移植内核**：只挑上面列的算法与规格，几何仍交给 AutoCAD。
4. 移植任何代码前，先把 `ATTRIBUTION.md` 建起来（`cc.attribution` 那 2h 就是干这个的）。

## 明确不挖

| 不挖 | 为什么 |
|---|---|
| crates/render + crates/ui-egui + apps/cadcraft 的窗口/主题/动画/spacemouse | 我们是 headless 自动化，界面与渲染交给 AutoCAD |
| apps/cadcraft-web（WASM/Trunk/上传下载） | 目标平台是 Windows 桌面 + AutoCAD，Web 版无收益 |
| 几何内核的整体移植（crates/geom 全套） | 几何由 AutoCAD 提供；只挑具体算法（偏移/求交/圆角），不搬内核 |
| 打包/图标/本地化/Homebrew/flatpak 等分发细节 | 我们不分发给终端用户 |
| clean-room 法律隔离流程（法律文档本身） | 我们不是复刻项目；只需遵守 MIT/Apache 的署名义务 |
