# `_contrib`：从 CAD-Agent-Hub 收进来的"本机还没法验收"的部分

这些内容不是 nsa-mcp-hub 的运行时组件，而是**从 CAD-Agent-Hub 迁移过来、等有环境再接**的资产。
按"能不能真机验收"分三档：

| 目录 | 来源 | 本机状态（2026-11-04 实测） | 接入方式 |
|---|---|---|---|
| `ansys-structural-workbench/` | `CAD-Agent-Hub/skills/` | **未安装 ANSYS**（`C:\Program Files\ANSYS Inc` 不存在） | 装了 ANSYS 之后按 skill 里的步骤跑；要不要做成 `ansys` kit 等确认许可再定 |
| `fusion/electronics_write_bridge/` | `CAD-Agent-Hub/` | **未安装 Fusion 360**（`%LOCALAPPDATA%\Autodesk\webdeploy` 不存在） | Fusion 的本地写入桥，接 Fusion 时再启 |
| `fusion/fusion_starship_v3_builder.py` | `CAD-Agent-Hub/` | 同上 | Fusion API 的参数化建模示例（Starship v3） |
| `models/` | `CAD-Agent-Hub/models/` | 纯 Python 示例（build123d/cadpy） | 参考用；等价能力已由 `sw_gear_involute_plan`、`sw_output_shaft_plan`、`sw_part_plan` 提供 |

## 为什么没有直接做成 kit

nsa-mcp-hub 的约定是"**工具必须给判据、判据必须真机可验**"。ANSYS 与 Fusion 本机都没装，
硬接进来只能得到一堆永远 SKIP 的工具，反而污染工具表。所以这三块留在 `_contrib`，
等有软件许可时按上面的接入方式转成正式 kit（catia 就是这么做的：工具面已接进网关，
本机没 CATIA 所以验收 SKIP）。

## 已经接进网关但没有真机验收的

- `ug`（`CAD-Agent-Hub/MCP/UG`，82 个工具）：CAM / 机床运动学 / NX 钣金 / 装配约束写入。
  需要 NX 交互式会话 + `nx_user/startup` 里的 `NXMcPRemotingServer.dll` 被加载
  （把 `UGII_USER_DIR` 指到 `CAD-Agent-Hub/MCP/UG/nx_user`），并在 NX 里跑过一次
  `start_mcp.py` 把 socket 桥起来。桥没起时工具会如实报错，不会假装成功。
- `catia`（`CAD-Agent-Hub/MCP/CATIA`，55 个工具）：本机未安装 CATIA V5，验收 SKIP。
