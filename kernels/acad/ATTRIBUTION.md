# 署名与来源（ATTRIBUTION）

本文件登记 nsa-toolchain/kernels/acad（acadkit）**从外部项目吸收的内容**。
原则：只登记真正吸收的东西；吸收方式与许可证义务写清楚。

## 上游：CADCraft

- 仓库：<https://github.com/beclab/cadcraft>
- 许可证：**MIT OR Apache-2.0**（双许可，可择一遵守）
- 与我们路线的关系：CADCraft 是"重写内核"，我们是"驱动真机 AutoCAD"。**几何内核我们不用**，
  只吸收算法、行为规格与数据模型。清单见 [`docs/CADCRAFT_MINE.md`](docs/CADCRAFT_MINE.md)。

### 已吸收（按吸收方式分类）

| 方式 | 内容 | 落地位置 | 义务 |
|---|---|---|---|
| 方法 | 覆盖率量化（加权 + 分受众 + 明写分母） | `tools/gen_parity.py` / `docs/PARITY.md` | 思路借鉴，无代码 |
| 方法 | 缺口账本（工时 + 影响排序） | `tools/gen_gaps.py` / `docs/GAPS.md` | 思路借鉴，无代码 |
| 方法 | 工作流级 alpha gate（不是能力级） | `tools/alpha_gate.py` / `docs/ALPHA_GATE.md` | 思路借鉴，无代码 |
| 方法 | 挖掘全量清单先行（先总量再动手） | `docs/backlog.yaml` / `docs/cadcraft_mine.yaml` | 思路借鉴，无代码 |
| 规则 | 程序化调用不得弹对话框 / 输入即敌意 / 每次修复带回归测试 | `AGENTS.md` §5–§7 | 文字改写，注明来源 |
| 规则 | 分层 + everything-is-a-command | 本仓库 `caps.py` 单一入口（早已同构） | 无代码 |

### 计划吸收（落地时逐条补充来源文件与作者）

见 `docs/CADCRAFT_MINE.md` 的批次表。**每落地一条 `移植` 项，必须在这里加一行**：
上游文件路径、作者（GitHub handle）、许可证、我们改写的位置。

## 我们自己的声明

- 本仓库**不包含**任何 Autodesk、Adobe 或第三方的图标、字体（SHX）、填充图案（`.pat`）、
  线型（`.lin`）、模板、菜单（CUI/PGP）或帮助文本。
- 驱动 AutoCAD 时用它自带的字体与图案**是运行时行为**，不构成再分发。
- 生成的图纸/PDF/DWG 由 AutoCAD 产出，仓库里只放示例小文件。

## 复核

每吸收一条新的外部内容（代码/算法/规格），在同一提交里更新本文件；
`tools/parity_scan.py` 会在 CI 里检查"清单里有 port 项但本文件没提"的情况（见下）。
