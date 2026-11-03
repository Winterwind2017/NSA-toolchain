# EPLAN kit（`eplan_*`，67 个工具的能力面）

上游：`CAD-Agent-Hub/MCP/EPLAN`（GitHub `Cai-aa/CAD-Agent-Hub`，基线 `c051b72`）。
本 kit 是**代理**：hub 起 `MCP/EPLAN/server.py`，把它的工具面整体接进来，前缀 `eplan_`。

## 为什么补这一块

2026-11-04 做的差集：

| kit | 上游 | hub（补之前） | 缺 |
|---|---|---|---|
| ug | 82 | 84 | 0 |
| catia | 55 | 57 | 0 |
| sw | 40 | 177 | 19（其中 8 个是真能力，见 `docs/upstream-ug-cam-patch.md`） |
| **eplan** | **67** | **0** | **整块缺失** |

所以 EPLAN 是唯一"整块没有"的能力面，优先级最高。

## 画像（profile）：默认只读，写操作要显式开

| `EPLAN_MCP_PROFILE` | 工具数 | 说明 |
|---|---|---|
| `review`（默认） | **17** | 工程/页/功能只读、bridge 发现、能力自报、工具目录、离线审图 |
| `trial` | **77** | 加 55 个 `eplan_trial_*`：放置电机/继电器/端子、连互锁、导出 PDF…… **仍限定在固定可丢弃工程内** |

默认用 `review` 是刻意的：这套 kit 的写操作只允许在 trial 工程里，且要先 `bridge_hello` 校验构建号。

## 前置条件

1. 装了 EPLAN 2.9（本机：`C:\Program Files\EPLAN\Common`，`EPLAN Client Service` 在跑）；
2. 读真实工程要有**原生 bridge**（`eplan_bridge_discover` 能列出实例）。
   没开 EPLAN 时 `instances: []` —— 这是**正常结果**，不是失败；
3. 可选环境变量：
   - `EPLAN_MCP_WORKSPACE`：工作目录（缺省用上游默认）；
   - `EPLAN_MCP_PROFILE`：`review` / `trial`；
   - `EPLAN_EXE`：EPLAN 可执行文件绝对路径（`eplan_capabilities` 里 `configured_executable` 用它）。

## 怎么用

```bash
python -m nsa_mcp_hub.servers.eplan_mcp        # 单独起
_tools\nsa-mcp-hub-eplan.cmd                   # Windows 包装
```

聚合网关里它就是一个 kit：`KITS["eplan"]`，工具名前缀 `eplan_`。

| 工具 | 用途 | 判据 |
|---|---|---|
| `eplan_capabilities` | 画像 / 版本约束 / 支持与不支持清单 | `reads.profile == "review"`、`reads.server == "eplan29-lab"` |
| `eplan_tool_catalog` | 当前画像下的工具目录 | `reads.count == 15`（review） |
| `eplan_bridge_discover` | 发现本用户的原生 bridge 实例 | `ok=True`，EPLAN 没开时 `instances=[]` |

## 验收

```
=== eplan（nsa_mcp_hub.servers.eplan_mcp）===
  PASS eplan.capabilities      46 ms
  PASS eplan.tool_catalog       3 ms
  PASS eplan.bridge.discover    3 ms
eplan：3/3 通过（0.9s）
报告：_runs/acceptance-20261104-031521.json
```

没装 EPLAN 的机器靠 `skip_if` 整组跳过（检测 `C:\Program Files\EPLAN`）。

## 已知边界

* `eplan_runtime_status` 会做**源码指纹比对**（加载时字节 vs 磁盘字节），
  一旦我改过上游文件它就会返回 `ok=False` —— 这是它设计上的保护，不是坏了；
* 写操作（`eplan_trial_*`）只在 `trial` 画像 + 固定 trial 工程 + 校验过的构建号下允许，
  `eplan_capabilities` 里 `native_writes: "disabled"` 说的就是 review 画像；
* 读真实工程需要 bridge；没有 bridge 时只能做离线部分（能力自报、工具目录、审图 schema）。
