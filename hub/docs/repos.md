# 仓库地图

> **2026-11-09 起：软件自动化相关的 13 个仓已合并成一个 monorepo**
> [`nsa-toolchain`](https://github.com/Winterwind2017/nsa-toolchain)
> （6 内核 + 网关 + 6 技能）。旧的单仓**全部归档**（只读保留历史），
> 内容与提交历史都已并入 monorepo，老路径在本地是目录联接。
> 迁移细节见 monorepo 的 `docs/MIGRATION.md`。

这条工具链按**「内核 / 技能 / 工作台 / 资产」分层**，但内核与技能现在同处一个仓：

```
nsa-toolchain/
  kernels/{sw,acad,nx,gx,codesys,autoshop}   6 个内核（原 6 个单仓）
  hub/                                       聚合网关（原 nsa-mcp-hub）
  skills/ww-* automation                     6 个 agent 技能（原 6 个单仓）
  docs/ scripts/                             仓级文档与迁移/校验脚本
```

> **NSA = Non-standard automation（非标自动化）**：整条链的目标是让做非标自动化设备设计的工程师，
> 能更方便地驱动手边这些软件，把重复的建模 / 出图 / 编号 / 编程动作交给 agent。

## 一、monorepo 内部：内核与网关

每个内核都是「库 + CLI + MCP」，每个宣称可用的能力都在 registry 里附判据；`hub/` 把它们接成**一个 MCP 端点**。

| 目录 | 对应软件 | 说明 |
|---|---|---|
| `hub/` | — | **总入口**：统一返回结构与验收口径（`python -m nsa_mcp_hub.servers.nsa_hub_mcp`） |
| `kernels/sw/` | SolidWorks 2025 | 建模、装配、钣金、出图；`swkit` |
| `kernels/acad/` | AutoCAD 2025 | 二维绘图/标注/表格/图框/三维实体；`acadkit` |
| `kernels/nx/` | UG NX 2512 | journal 建模、装配、制图、CAM；几何判据 |
| `kernels/gx/` | GX Works3 | FX5U/iQ-R 工程：新建、写 ST、编译诊断、标签、另存 |
| `kernels/codesys/` | CODESYS 3.5 | 常驻服务 + token 鉴权 + 免 COM 注册 |
| `kernels/autoshop/` | AutoShop V4.11 | `.hcp` 编解码、`.LD` 图解码、H5U IL、UI 自动化 |

## 二、monorepo 内部：Agent 技能

技能只写“判断与坑”，不重复内核文档；内核升级时技能文本不必跟着改。

| 目录 | 对应内核 |
|---|---|
| `skills/ww-solidworks-automation/` | `kernels/sw` |
| `skills/ww-autocad-automation/` | `kernels/acad` |
| `skills/ww-nx-automation/` | `kernels/nx` |
| `skills/ww-gxworks-automation/` | `kernels/gx` |
| `skills/ww-codesys-automation/` | `kernels/codesys` |
| `skills/ww-autoshop-automation/` | `kernels/autoshop` |

## 三、仍然是独立仓库的（不属于上面那条链）

| 仓库 | 说明 |
|---|---|
| [`Non-standard-automation-design`](https://github.com/Winterwind2017/Non-standard-automation-design) | 非标自动化设计工作台（设计流程、规则、案例） |
| [`workspace-assets`](https://github.com/Winterwind2017/workspace-assets) | 工作区级共享资产（`.agents`、mcp-cad-bridge、projects、skill-health） |
| [`global-assets`](https://github.com/Winterwind2017/global-assets) | 全局共享资产（cad_framework、design_knowledge、plugins、skills） |
| [`skill-nonstandard-project-manager`](https://github.com/Winterwind2017/skill-nonstandard-project-manager) | 非标项目管理技能 |
| [`skill-management-advisor`](https://github.com/Winterwind2017/skill-management-advisor) | 管理类技能 |
| [`value-investing-skills`](https://github.com/Winterwind2017/value-investing-skills) | 价值投资分析技能 |
| [`ww-obsidian`](https://github.com/Winterwind2017/ww-obsidian) | Obsidian 笔记库技能（obsidiankit，只读体检/检索） |
| [`ww-obsidian-agent`](https://github.com/Winterwind2017/ww-obsidian-agent) | Obsidian 内的对话插件（**不是**技能，跟上面那个不是一回事） |
| [`dsh-sidebar-edge`](https://github.com/Winterwind2017/dsh-sidebar-edge) | DSH 侧边栏插件 |

## 怎么按主题找

monorepo 内部按目录找；仓库级检索靠 GitHub Lists（见下）。
各仓仍然打了 topics，常用：`nonstandard-automation` / `mcp` / `agent-skills` / `cad` / `plc`，
以及按软件分的 `solidworks` / `autocad` / `siemens-nx` / `gx-works3` / `codesys` / `autoshop`。

```bash
# 例：列出所有打了 nonstandard-automation 的仓库
gh search repos --owner Winterwind2017 --topic nonstandard-automation --limit 50
```

## 为什么 profile 上没有 Pinned

所有仓库都是私有的，而 GitHub 只允许 pin **公开**仓库（`viewer.pinnableItems` 实测 `totalCount = 0`）。
所以归集走 **GitHub Lists**（支持私有仓）：`https://github.com/Winterwind2017?tab=lists`
——工具链 / 工作台与资产 / 其它技能 三组。

## 可见性

**全部仓库均为私有（private）。** 这里的「发布 vX.Y.Z」只表示打 git tag + 推 main，不改变可见性；
复核：`python scripts/assert_private_repos.py`。
