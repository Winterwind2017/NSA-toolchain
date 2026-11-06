# nsa-mcp-hub

把多个 CAD / PLC 自动化内核统一成 **一个 MCP 端点**，并且**用判据（checks）决定成败**，而不是用“调用没报错”决定成败。

这个仓库是我在日常非标自动化设计、出图、PLC 编程中沉淀下来的一层基础设施：每个软件背后是一套独立内核（AutoCAD、SolidWorks、NX、GX Works3、CODESYS、汇川 AutoShop、CATIA、EPLAN），hub 负责把它们接成统一的工具面、统一的返回结构、统一的验收口径。

## 设计目标

| 目标 | 做法 |
|---|---|
| 一款软件坏了不影响其它 | 每个 kit 独立进程 / 独立适配器；`nsa_hub_status` 逐 kit 报存活与最近错误 |
| 结果可验证 | 每个工具返回 `{ok, reads, checks, errors}`；`requires_checks` 的工具若 `checks` 为空**直接判负** |
| 并发安全 | 同一台机器多进程驱动同一软件时用**文件锁**单飞；工具可声明 `lock_free` 旁路 |
| 可重放 | 幂等工具接受 `request_id`，重复调用回放上次结果 |
| 卡死可诊断 | 超时会话显式记进 `_stuck`，不假装完成；`NSA_MCP_HUB_DUMP_STACKS=1` 可转储线程栈 |

## 架构

```
MCP 客户端
   │  (stdio, MCP 2025-06-18)
   ▼
nsa_mcp_hub.servers.nsa_hub_mcp      ← 聚合入口：一个进程承接全部 kit
   ├─ native adapter ──► 进程内 import 内核（acadkit / nxkit / swkit / gxkit / codesyskit / autoshopkit）
   ├─ proxy kit     ──► 子 MCP 进程（CATIA / EPLAN / NX 扩展服务端，路径由 CAD_SERVERS_HOME 指定）
   └─ 每个 kit 也可以单独起一个 MCP 入口：servers.<kit>_mcp
```

- `Kit`：工具名前缀、人类可读名、版本、工具表、单飞锁、运行统计。
- `ToolSpec`：输入 schema、handler、超时、`idempotent` / `lock_free` / `must_have_checks`、字段级 validator。
- 所有工具输出经 `normalize()` 收敛成同一形状，客户端不需要为每个 kit 写不同解析。

## 安装

```bat
git clone git@github.com:Winterwind2017/nsa-mcp-hub.git
cd nsa-mcp-hub
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e .
```

内核（各 kit 的实现）是独立仓库，按需放到本机后由环境变量指过去即可，见下表。

## 运行

聚合入口（推荐，一个 MCP 条目拿到全部工具）：

```bat
.venv\Scripts\python -m nsa_mcp_hub.servers.nsa_hub_mcp
```

单 kit 入口（只想要某一款软件时）：

```bat
.venv\Scripts\python -m nsa_mcp_hub.servers.sw_mcp
.venv\Scripts\python -m nsa_mcp_hub.servers.acad_mcp
.venv\Scripts\python -m nsa_mcp_hub.servers.nx_mcp
```

`_tools\*.cmd` 是 Windows 下的直接启动脚本；`gh`/MCP 客户端里把命令指向其中之一即可。

## 环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `SWKIT_SRC` | swkit 源码目录（SolidWorks 内核） | `%USERPROFILE%\solidworks-agent-kit\src` |
| `ACADKIT_SRC` | acadkit 源码目录（AutoCAD 内核） | `%USERPROFILE%\acadkit\src` |
| `NXKIT_SRC` | nxkit 源码目录（NX 建模内核） | `%USERPROFILE%\nxkit\src` |
| `GXKIT_SRC` / `CODESYSKIT_SRC` / `AUTOSHOPKIT_SRC` | 对应内核源码目录 | 同上规则 |
| `CAD_SERVERS_HOME` | 三个 proxy kit（CATIA / EPLAN / NX 扩展）的服务端根目录 | `%USERPROFILE%\cad-servers` |
| `SW_PATCH_DIR` / `SW_PATCH_PYTHON` | swkit 脚本类工具（分步 FEA / Motion / 批量扫描）所在目录与解释器 | 仓库内 `mcp-patches` |
| `UGII_BASE_DIR` | NX 安装根（proxy kit 需要） | 由 NX 安装程序设置 |
| `NX_MCP_ALLOW_EXECUTE` | 是否允许 NX 侧执行任意 Python（默认开，谨慎） | `1` |
| `EPLAN_MCP_PROFILE` | EPLAN 服务端工作模式 | `review` |
| `NSA_MCP_HUB_TIMEOUT_SCALE` | 全局超时缩放（调试慢机器用） | `1.0` |
| `NSA_MCP_HUB_RUNS` | 验收/契约运行记录目录 | 仓库内 `_runs` |

## 工具面（9 个 kit）

| kit key | 名称 | 宿主软件 | 接法 | 工具数（参考） |
|---|---|---|---|---|
| `sw` | swkit | SolidWorks 2025 | 子 MCP + hub 侧脚本/特征层 | 192 |
| `acad` | acadkit | AutoCAD 2025 | 进程内（COM） | 55 |
| `nx` | nxkit | NX 2512 | 进程内（`run_journal` 批处理） | 66 |
| `ug` | NX 扩展服务 | NX 2512 | proxy（.NET remoting 挂活会话） | 88 |
| `gx` | gxkit | GX Works3 | 进程内（UIA + 前台窗口） | 47 |
| `codesys` | codesyskit | CODESYS 3.5 | 进程内（常驻服务） | 60 |
| `autoshop` | autoshopkit | AutoShop V4.11 | 进程内（UIA / frida） | 42 |
| `catia` | CATIA 服务 | CATIA V5 | proxy | 56 |
| `eplan` | EPLAN 服务 | EPLAN 2.9 | proxy | 16 |

合计约 620 个工具。数量随宿主软件版本、是否在线、以及本机内核版本浮动；工具名一律带 kit 前缀（`sw_`、`acad_`、`ug_` …），便于路由。

> proxy kit 的服务端源码不在本仓库内：它们是**可插拔的外部服务**，用 `CAD_SERVERS_HOME` 指到本机目录。没准备好时该 kit 只暴露 `<前缀>_unavailable` 诊断工具并说明原因，**其余 kit 不受影响**。

## 目录结构

```
nsa_mcp_hub/
  server.py / hub.py / tools.py / jsonrpc.py / mcpclient.py / contracts.py
  servers/            每个 kit 一个 MCP 入口
  adapters/           适配器：native（进程内）/ proxy（子 MCP）
  acceptance/         真机验收用例（按 kit 分组）
scripts/              验收、契约 sweep、覆盖率报告、proxy venv 准备
docs/                 工具面清单、验收矩阵、各 kit 专项说明
tests/                协议/工具/服务器级测试（不依赖宿主软件的那部分）
```

## 测试与验收

```bat
.venv\Scripts\python -m pytest tests -q                 :: 协议与工具层，离线可跑
.venv\Scripts\python scripts\contract_sweep.py          :: 工具契约 sweep
.venv\Scripts\python scripts\coverage_report.py         :: 覆盖汇总
.venv\Scripts\python scripts\setup_proxy_venvs.py --check   :: proxy 服务端独立 venv 体检
```

真机验收用例需要对应软件在场；不在场时用例会失败或跳过，而不是假装通过——这是刻意设计。

## 版本

### v0.2.0

补上了一整层**纯几何 / 特征图**能力（全部自带实现、不依赖 SolidWorks 在场即可编译与校验）：

| 模块 | 作用 | 配套工具 |
|---|---|---|
| `feature_graph` | Feature Graph IR 的校验与编译，输出确定性步骤表 | `sw_feature_graph_compile` |
| `part_generators` | block / cylinder / tube / flange / stepped_shaft | `sw_part_plan`、`sw_create_parametric_part` |
| `involute_gear` | 渐开线直齿轮（采样齿廓 + 环形阵列） | `sw_gear_involute_plan`、`sw_create_involute_gear` |
| `gearbox` | 两级平行轴减速器（16 个特征整机） | `sw_gearbox_plan`、`sw_create_two_stage_reducer` |
| `output_shaft` | 按图纸的输出轴（13 个特征、333 mm） | `sw_output_shaft_plan`、`sw_create_output_shaft` |
| 特征树编辑 | 特征树读写、参数修改、回滚 | `sw_feature_inspect`、`sw_feature_rollback`、`sw_set_feature_parameter`、`sw_select_references` |

真机验证（SolidWorks 33.4.1 / SP4.1，全部为**几何读数**，不是"调用没报错"）：

| 用例 | 判据 | 实测 |
|---|---|---|
| Feature Graph 建块 100×60×20 | 体积 120000 mm³ | 120000.0 |
| 齿轮 m2 z20（含齿形阵列） | 9 特征、单一实体 | 9 特征 / 1 solid |
| 两级减速器 | 16 特征、7 个实体 | 16 特征 / 7 solids |
| 输出轴 333 mm | 13 特征、体积与解析值同量级 | 13 特征 / 768065.6 mm³ |

判据是数学与结构，不依赖界面：齿轮按 `da=m(z+2)`、`df=m(z−2.5)`、`db=d·cosα` 核对四个特征圆；
减速器按传动比 `(z2/z1)(z4/z3)` 与中心距 `a=m(z1+z2)/2` 核对；输出轴按图纸总长与七段直径核对；
零件生成器核对特征数与参数回显。

### v0.1.0

首个版本：hub 框架、9 个 kit 入口、适配器、验收框架、脚本、文档。

路线图：

1. 把几何层继续做深（斜齿轮、内齿轮、花键轴、键槽标准库）；
2. 继续扩充各 kit 的真机验收覆盖面；
3. 为 proxy kit 提供统一的服务端接口约定，降低接入成本。

## 许可

MIT，见 `LICENSE`。
