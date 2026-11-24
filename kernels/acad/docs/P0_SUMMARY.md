# P0 结论：AutoCAD 能不能做成第二个 swkit 内核？

> **注（2026-10-21）**：本文件是 P0 当时的快照（registry 60 条）。
> P1 全部做完后 registry 为 **62 条 = 50 verified + 8 dead + 4 external**，
> 内核实现 52 条能力、真机 52/52 通过 —— 以
> [`P1_PROGRESS.md`](P1_PROGRESS.md) 与 [`registry.yaml`](registry.yaml) 为准；
> 下面写的"P1 建议"已完成，保留作决策记录。

**能。** 底料比 SolidWorks 起步时更多，但失败模式不同——难点在判据与环境，不在"能不能调"。

## 一、盘点结果（本机实测，非估算）

| 资产 | 规模 | 性质 |
|---|---|---|
| `autocad-mcp` | 8 工具 / **96 子操作** / 3 后端 / **123 个 pytest** | 正规包，MCP-first、无 CLI |
| `acad_mech_build.py` | **170 KB / 37 函数** | 机械制图实战层（公差表/投影引擎/BOM/多布局） |
| `acad_ext_mcp.py` | **73 个 TOOLS 键** | 扩展层（图层状态/表格/多行文字/Plot/NetAPI…） |
| `acad_plc_build.py` + `acad_ae_*` | ~270 KB | 电气 / PLC |
| `ACAD_MECH_CAPABILITY.md` | 17 KB | 已有能力矩阵 + 硬缺口（本文件的基础） |
| `ACAD_DEV.md` | 571 KB | 踩坑全集 |

## 二、registry 种子（`docs/registry.yaml`）

**60 条能力**，逐条标注后端、状态、判据草案、证据出处：

| 状态 | 条数 | 含义 |
|---|---|---|
| `verified` | **30** | 实测可用，且判据能说清（不过目前判据是**文字草案**，P1 才落成代码） |
| `usable_unjudged` | **22** | 实测可用，但还没有几何判据 → **P1 主要工作量在这里** |
| `pending` | **2** | 有实现未验证（`geom.spline`、`boolean.section_slice`） |
| `dead` | **6** | 本机无法用官方功能实现，已写替代方案 |

后端覆盖：`com` 48 · `lisp` 31 · `headless` 14 · `file` 2 · `python` 1 · `csg` 1。

> 关键含义：**没有一条能力只有单一后端可选**（除了 dead）。这对内核是好消息——
> 任意后端挂了都还有退路；对实现是坏消息——每条都要声明后端，不能想当然。

### 6 条 dead（都是官方缺口，不是我们没做）

| 缺口 | 原因 | 替代 |
|---|---|---|
| `constraint.geometric` | 完整版 AutoCAD 也无 `GEOMCONSTRAINT`/`DIMCONSTRAINT` | Python 侧参数驱动重建 |
| `export.pdf_multipage` | `-PUBLISH` 在 GUI/accoreconsole 都阻塞 | 每布局一份 PDF，或外挂 PDF 合并 |
| `view.projection_builtin` | `SOLVIEW`/`SOLDRAW`/`SOLPROF`/`FLATSHOT` 全不存在 | **已自建 CSG 投影引擎** |
| `dim.update` | `DIMUPDATE` 命令不存在 | 重建标注或改属性 |
| `block.edit_inplace` | `BEDIT`/`ATTSYNC`/`ATTREDEF`/`BATTMAN` 全不存在 | 重定义 + 重插 |
| `interfere` | `INTERFERE` 命令不存在 | 布尔求交后看体积 |

## 三、与 swkit 的三处结构性差异

| 维度 | swkit（SolidWorks） | acadkit（AutoCAD） |
|---|---|---|
| 执行路径 | **1 条**（COM） | **3+1 条**（com / lisp / headless / file，另加 csg 纯计算） |
| 判据形态 | 体积/面数/包围盒 | 计数 → 属性读回 → **重开文件复核**（四级，见 `JUDGE_SPEC.md`） |
| 主要风险 | **几何假成功**（建壳无肉） | **几何假成功 + 环境污染**（profile/TRUSTEDPATHS/.sv$ 残留） |

第三条是最容易被低估的：swkit 最坏情况是"模型没变"；acadkit 最坏情况是
**"模型变了，但你本机的 AutoCAD 配置被改坏了"**（历史上真的发生过三次）。

## 四、P0 交付物

```
<repo>\acadkit\
├─ docs\
│  ├─ registry.yaml        60 条能力（后端/状态/判据/证据）
│  ├─ BACKEND_MATRIX.md    4 条执行路径 × 20 个能力族 + 选择规则
│  ├─ JUDGE_SPEC.md        判据四级 + 按族模板 + 环境自检 + 负面对照
│  ├─ P0_SUMMARY.md        本文件
│  └─ _extract.json        结构化抽取结果（机器可读）
└─ tools\
   ├─ extract_caps.py      从三处源码抽能力（只读）
   └─ stats_registry.py    统计 registry 分布（数字不手写）
```

## 五、P1 建议（在新窗口做）

| 步 | 内容 | 产出 |
|---|---|---|
| 1 | 包骨架 `src/acadkit/`：`core/`（COM 晚绑定 + profile 守卫 + clean_quit）、`backends/`（com/lisp/headless 路由）、`registry.py`（从 yaml 载入） | 能 `acadkit status` 并自检环境 |
| 2 | `judges/`：按 `JUDGE_SPEC.md` 的四级判据，先做 8 个（线/圆/标注/块属性/表格/布尔/导出/投影） | 判据可复用 |
| 3 | 把 `verified` 的 **30 条**里的前 12 条落成 CLI + 真机用例 | 回归套件雏形 |
| 4 | 环境自检接入每个用例（前后各一次） | 防环境污染 |
| 5 | 补 `usable_unjudged` 22 条到 L2 判据 | 转正 |

**估时**：步骤 1–2 约 1 天；3–4 约 1.5 天；5 约 1.5 天。合计 **4 天左右**能到
"30 条 verified + 22 条有判据"的水平（swkit 用了 ~30 天才到 150 条，
因为 SW 的 API 要一条条试；AutoCAD 这边能力已经在手，主要是补判据）。

## 六、必须先定的一个规矩

`acadkit` **不注册第二个 AutoCAD MCP**。与 `autocad-mcp` 的关系是：

```
acadkit 内核（库 + CLI）
   ├─ 复用 autocad-mcp 的后端（不另起 MCP 服务）
   ├─ 吸收 acad_mech_build / acad_plc_build / acad_ext_mcp 的配方
   └─ 对外 CLI 优先；MCP 面与 autocad-mcp 二选一
```

理由：一软件只留一个最强 MCP，两个 MCP 同时连 AutoCAD 会互相抢文档与命令队列。
