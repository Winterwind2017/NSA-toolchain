# 仓库地图

这条工具链不是一个大仓，而是**按“内核 / 技能 / 工作台 / 其它”分层的多仓结构**。
为什么拆开：每个内核都要跟一款具体软件的版本、许可证、装机目录绑定（AutoCAD 2025、SolidWorks 2025、
NX 2512、GX Works3、CODESYS 3.5、AutoShop V4.11），混在一个仓里既没法独立发版，也没法各自跑验收；
技能（skill）则是“怎么用、别踩什么”的说明，跟内核的发版节奏完全不同。

> **NSA = Non-standard automation（非标自动化）**：整条链的目标是让做非标自动化设备设计的工程师，
> 能更方便地驱动手边这些软件，把重复的建模 / 出图 / 编号 / 编程动作交给 agent。

## 一、适配内核（真正干活的那层）

每个都是「库 + CLI + MCP」，每个宣称可用的能力都在 registry 里附判据。

| 仓库 | 对应软件 | 说明 |
|---|---|---|
| [`nsa-mcp-hub`](https://github.com/Winterwind2017/nsa-mcp-hub) | — | **总入口**：把下面这些内核接成一个 MCP 端点，统一返回结构与验收口径 |
| [`solidworks-agent-kit`](https://github.com/Winterwind2017/solidworks-agent-kit) | SolidWorks 2025 | 建模、装配、钣金、出图；`swkit` |
| [`autocad-agent-kit`](https://github.com/Winterwind2017/autocad-agent-kit) | AutoCAD 2025 | 二维绘图/标注/表格/图框/三维实体；`acadkit`（本地目录名 `acadkit`） |
| [`nxkit`](https://github.com/Winterwind2017/nxkit) | UG NX 2512 | journal 建模、装配、制图、CAM；几何判据 |
| [`gxkit`](https://github.com/Winterwind2017/gxkit) | GX Works3 | FX5U/iQ-R 工程：新建、写 ST、编译诊断、标签、另存 |
| [`codesyskit`](https://github.com/Winterwind2017/codesyskit) | CODESYS 3.5 | 常驻服务 + token 鉴权 + 免 COM 注册 |
| [`autoshopkit`](https://github.com/Winterwind2017/autoshopkit) | AutoShop V4.11 | `.hcp` 编解码、`.LD` 图解码、H5U IL、UI 自动化 |

## 二、Agent 技能（告诉 agent 怎么用）

技能只写“判断与坑”，不重复内核文档；内核升级时技能文本不必跟着改。

| 仓库 | 对应内核 |
|---|---|
| [`ww-solidworks-automation`](https://github.com/Winterwind2017/ww-solidworks-automation) | solidworks-agent-kit |
| [`ww-autocad-automation`](https://github.com/Winterwind2017/ww-autocad-automation) | autocad-agent-kit |
| [`ww-nx-automation`](https://github.com/Winterwind2017/ww-nx-automation) | nxkit |
| [`ww-gxworks-automation`](https://github.com/Winterwind2017/ww-gxworks-automation) | gxkit |
| [`ww-codesys-automation`](https://github.com/Winterwind2017/ww-codesys-automation) | codesyskit |
| [`ww-autoshop-automation`](https://github.com/Winterwind2017/ww-autoshop-automation) | autoshopkit |

## 三、工作台与资产

| 仓库 | 说明 |
|---|---|
| [`Non-standard-automation-design`](https://github.com/Winterwind2017/Non-standard-automation-design) | 非标自动化设计工作台（设计流程、规则、案例） |
| [`workspace-assets`](https://github.com/Winterwind2017/workspace-assets) | 工作区级共享资产 |
| [`global-assets`](https://github.com/Winterwind2017/global-assets) | 全局共享资产 |
| [`skill-nonstandard-project-manager`](https://github.com/Winterwind2017/skill-nonstandard-project-manager) | 非标项目管理技能 |
| [`skill-management-advisor`](https://github.com/Winterwind2017/skill-management-advisor) | 管理类技能 |

## 四、其它

| 仓库 | 说明 |
|---|---|
| [`ww-obsidian`](https://github.com/Winterwind2017/ww-obsidian) | Obsidian 笔记库技能（只读体检/检索） |
| [`ww-obsidian-agent`](https://github.com/Winterwind2017/ww-obsidian-agent) | 同上，agent 版本 |
| [`value-investing-skills`](https://github.com/Winterwind2017/value-investing-skills) | 价值投资分析技能 |
| [`dsh-sidebar-edge`](https://github.com/Winterwind2017/dsh-sidebar-edge) | DSH 侧边栏插件 |

## 怎么按主题找

全仓都打了 topics，点任意仓库顶部的 topic 就能横向筛，常用几个：

- `nonstandard-automation` —— 整条 NSA 链（内核 + 技能 + 工作台）
- `mcp` / `mcp-server` —— 能被 MCP 客户端直接接的入口
- `agent-skills` —— 技能类仓库
- `cad` / `plc` —— 按专业分
- `solidworks` / `autocad` / `siemens-nx` / `gx-works3` / `codesys` / `autoshop` —— 按软件分

```bash
# 例：列出所有打了 nonstandard-automation 的仓库
gh search repos --owner Winterwind2017 --topic nonstandard-automation --limit 50
```

## 可见性

**全部仓库均为私有（private）。** 这里的「发布 vX.Y.Z」只表示打 git tag + 推 main，不改变可见性；
复核：`python scripts/assert_private_repos.py`。
