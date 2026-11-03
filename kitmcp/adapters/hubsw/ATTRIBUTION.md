# 第三方代码来源说明（ATTRIBUTION）

`kitmcp/adapters/hubsw/` 下的以下文件**复制自** [CAD-Agent-Hub](https://github.com/Cai-aa/CAD-Agent-Hub)：

| 文件 | 上游路径 |
|---|---|
| `contracts.py` | `MCP/Solidworks/src/solidworks_mcp/contracts.py` |
| `involute_gear.py` | `MCP/Solidworks/src/solidworks_mcp/involute_gear.py` |
| `gearbox.py` | `MCP/Solidworks/src/solidworks_mcp/gearbox.py` |
| `feature_graph.py` | `MCP/Solidworks/src/solidworks_mcp/feature_graph.py` |
| `part_generators.py` | `MCP/Solidworks/src/solidworks_mcp/part_generators.py` |
| `output_shaft.py` | `MCP/Solidworks/src/solidworks_mcp/output_shaft.py` |

上游许可：**MIT License**，Copyright (c) 2026 Cai-aa（全文见 `LICENSE.upstream`）。

## 为什么只搬这 6 个文件

上游的 SolidWorks MCP 共 40 个工具、约 20 个模块。这里只保留**零耦合**的子集：

- 引用 COM（`win32com` / `comtypes` / `Dispatch`）：**0 处**
- 引用 MCP SDK（`mcp` / `FastMCP`）：**0 处**
- 仅依赖标准库（`math` / `dataclasses` / `copy` / `typing`）

其余模块（`executor.py` 40 KB、`com_runtime.py`、`inspection.py`、`native_features.py`、
`interactive.py`、`server.py`）带有第二套 COM 客户端与 FastMCP 服务器壳，**没有搬**：
它们会和本机既有的 `swkit` COM 会话抢同一个 SolidWorks 实例，而且与 kitmcp 的
`{ok,reads,checks}` 契约不一致。执行层留待后续按需"映射到 swkit 现有 API"。

## 本地改动

- `__init__.py` 为本仓库新增（只做 re-export）。
- 上述 6 个文件**内容未改动**，保持与上游一致，便于以后对比升级。
