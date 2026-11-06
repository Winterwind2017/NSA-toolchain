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
| `sw` | swkit | SolidWorks 2025 | 子 MCP + hub 侧脚本/特征层 | 202 |
| `acad` | acadkit | AutoCAD 2025 | 进程内（COM） | 55 |
| `nx` | nxkit | NX 2512 | 进程内（`run_journal` 批处理） | 66 |
| `ug` | NX 扩展服务 | NX 2512 | proxy（.NET remoting 挂活会话） | 88 |
| `gx` | gxkit | GX Works3 | 进程内（UIA + 前台窗口） | 47 |
| `codesys` | codesyskit | CODESYS 3.5 | 进程内（常驻服务） | 60 |
| `autoshop` | autoshopkit | AutoShop V4.11 | 进程内（UIA / frida） | 42 |
| `catia` | CATIA 服务 | CATIA V5 | proxy | 56 |
| `eplan` | EPLAN 服务 | EPLAN 2.9 | proxy | 16 |

合计约 633 个工具。数量随宿主软件版本、是否在线、以及本机内核版本浮动；工具名一律带 kit 前缀（`sw_`、`acad_`、`ug_` …），便于路由。

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

### v0.8.0

检验尺寸从"算得出来"变成"落到图上、量得出来"。

| 改动 | 内容 |
|---|---|
| 检验注释 | 新工具 `sw_inspection_note`：把公法线/跨棒距/量球直径/齿厚写成**工程图注释**（没有工程图就新建一张），并**读回**注释文本校验数值确实在图上。四类零件都支持：外齿、内齿、斜齿、矩形花键 |
| 量柱/量球 | 不再用 `1.68·m` 经验值，而是按**接触点落在齿高中部反算**（和花键的做法统一）；结果里同时给出 `pin_diameter_rule` 与 `contact_radius_mm`，落点是否在真实齿面上也进了判据 |
| 判据修正 | 反算后外齿的 `α_M` 会**小于**压力角（接触点落到分度圆内侧）、内齿会**大于**，所以把"α_M ≥ α"换成**接触点必须落在齿顶/齿根之间**（斜齿按当量齿轮的半径比） |

实测（反算后的量具与读数）：

| 零件 | 量具 | 接触半径 | 跨距 |
|---|---|---|---|
| 外齿 m2 z20 | 量柱 Ø2.7896 | 19.75（齿高中部） | M = 42.2896（原 44.4498） |
| 内齿 m2 z40 | 量柱 Ø2.7772 | 40.25 | M = 77.7228（原 75.3662） |
| 斜齿 mn2 z24 β20 | 量球 Ø2.7791 | 28.67（当量齿 z_v=28.9237） | M = 60.1021（原 62.3236） |
| 花键 D46/d40 z8 b8 | 量柱 Ø8.455 | 21.5 | M = 51.454（本来已是反算） |

注释实测：四类零件的注释都写进了工程图（`document_type=3`），读回文本分别 179 / 140 / 144 / 121 字符，位置 `(0.06, 0.10)` 已设。

### v0.7.0

把"出图 → 检验"这条链闭合：斜齿轮给**法向**公法线与**量球**跨距，花键给**检具尺寸**。

| 能力 | 内容 |
|---|---|
| 斜齿轮检验 | 齿是拧着的，公法线只能沿**法向**量、跨棒距必须用**量球**（量柱会沿螺旋面滑）。按当量直齿轮算：`z_v = z/cos³β`、`m_n`、`α_n`，得 `W_nk` 与量球跨距 `M`，并在结果里注明测量方向 |
| 花键检具 | 矩形花键（GB/T 1144）给出齿厚 `b`、齿槽宽、**推荐量柱直径**、**跨棒距 M**——量柱夹在相对两个齿槽里，奇偶齿各自修正；量柱太细落到齿根圆上会被判为**无效量具**而不是给个数 |
| 工具面 | 新增 `sw_spline_inspection`；`sw_gear_inspection` 增加 `helix_angle_deg` 分支（200 → **201**） |

实测：

| 用例 | 判据 | 实测 |
|---|---|---|
| 斜齿 mn2 z24 β20 | z_v 28.9237、法向公法线 W4 = 21.4751、量球跨距 62.3236（球 Ø3.36） | 全部命中 |
| 花键 D46/d40 z8 b8 | 推荐量柱 Ø8.455、跨棒距 M = 51.454、接触方式 flank | 全部命中 |
| 负面对照 | 量柱 Ø1 太细 → 落底、`contact=root`，必须判失败 | 拒绝 ✅ |

### v0.6.0

三件收尾：把同类库的 loft 修复推上去、减速器键槽改成标准查表、齿轮族补上**检验尺寸**。

| 改动 | 内容 |
|---|---|
| 上游库修复已发布 | `solidworks-agent-kit` 的 `loft()` 参数错（14 → **18**）已推到该仓库 `main`（`3adc889`），并附带 registry 备注纠偏与文档重生成——预推送钩子的"文档与代码一致性"检查现在通过 |
| 减速器键槽 | 键宽/轴槽深不再硬编码，按 **GB/T 1096** 依轴径查表：Ø9.8 → 3×3/t1 1.8、Ø11.8 → 4×4/t1 2.5、Ø13.8 → 5×5/t1 3.0，键长取标准系列；规格写进 `metadata.keyways` |
| 齿轮检验尺寸 | 新工具 `sw_gear_inspection`：公法线长度 `W_k`、跨棒距 `M`（外齿 `+d_p`、内齿 `−d_p`，奇偶齿修正）、分度圆齿厚；齿轮与减速器的 plan 结果里都直接带 `inspection` |

公式与判据（真机不需要，纯数学但可交叉验证）：

```
k    = round(z·α/180° + 0.5)
W_k  = m·cosα·[π(k−0.5) + z·invα] + 2·x·m·sinα
invα_M = invα ± d_p/d_b ∓ π/(2z) ± 2x·tanα/z     （外齿取上加下减，内齿相反）
M    = d_b/cosα_M ± d_p                          （偶数齿；奇数齿乘 cos(π/2z)）
```

判据里有一条**基节不变式**：`W(k+1) − W(k)` 必须等于 `π·m·cosα`——它比"对不对得上表格"更能抓公式写错。

实测（m2 z20，α20°，x0）：齿厚 **3.1416**、公法线 `W3 = 15.3209`、跨棒距 **44.4498**（量柱 3.36）；
内齿 m2 z40：跨棒距 **75.3662**（α_M 17.2737°）；减速器总材积 **192279.689**（键槽加深后）。

### v0.5.0

两处收尾：**减速器齿轮换成真渐开线**，以及**修掉多实体体积只读第一个实体的老 bug**。

| 改动 | 内容 |
|---|---|
| 减速器齿轮 | 4 个齿轮改用 `tooth_outline_points` 的真渐开线轮廓（此前是"四顶点梯形"近似）；特征数仍是 16、实体数仍是 7 |
| 渐开线齿面起点 | 齿面从 `max(基圆, 齿根圆)` 起算——齿数大（约 z ≥ 42）时齿根圆在基圆外侧，旧写法会让轮廓先掉到基圆再回来形成小钩子（自交）；现在 z = 12/20/24/40/60/90 轮廓自交数全为 0 |
| 体积读数 | `body_volume_mm3` 改为**全部实体求和**，并新增 `body_count`；旧实现读 `bodies[0]`，减速器同一张图两次会读出 110963 和 11110（取决于实体创建顺序） |

真机读数：

| 用例 | 判据 | 实测 | 验收 |
|---|---|---|---|
| 减速器（渐开线） | 16 特征、7 实体、总材积 192448（±3%） | 16 / 7 / 192447.989 mm³ | PASS 84.0 s |
| 内齿圈（回归） | 体积 26325.888（±1%） | 26325.888 mm³ | PASS 27.3 s |
| 输出轴（回归） | 体积 768065.6（±2%） | 768065.6 mm³ | PASS 7.3 s |

另外修了同类库的一个真机 bug（独立仓库 `solidworks-agent-kit`）：`SolidWorksApp.loft()`
调 `InsertProtrusionBlend2` 只传 14 个参数（真签名 **18 个**），永远建不出特征。
修正后实测两块平行矩形放样体积 **28000.0 mm³**，与棱台公式一致；已记入该仓库
`docs/PITFALLS.md` 第 16 条。

### v0.4.0

把"齿轮族"做完整：内齿圈换成**真渐开线齿槽**，斜齿轮从"分层堆叠"改成**一次放样**（真螺旋面）。
为此给 Feature Graph IR 增加了 `loft_boss` 特征，执行器新增放样实现。

| 改动 | 之前 | 现在 |
|---|---|---|
| 内齿圈齿形 | 结构梯形（四顶点/齿） | **渐开线齿槽**：θ(r)=π/(2z)+inv(α_p)−inv(α_r)，齿根窄、齿顶宽；基圆以下用径向直线补齐 |
| 斜齿轮齿面 | 分层拉伸（台阶面，2N+3 特征） | **放样真螺旋面**（2N+4 特征，N 段截面绕轴递增扭转） |
| IR 特征种类 | 10 种 | **11 种**（新增 `loft_boss`：多截面按序放样，参数 `sections/closed/merge`） |

真机读数（SolidWorks 33.4.1）：

| 用例 | 判据 | 实测 | 验收 |
|---|---|---|---|
| 内齿圈（渐开线） | 体积 26325.888（±1%） | 26325.888 mm³ | PASS 19.3 s |
| 斜齿轮（4 段放样） | 体积 36290.5（±3%） | 36290.534 mm³ | PASS 57.0 s |

这两处都踩到真机坑，已固化进实现：

* `InsertProtrusionBlend2` 的**真签名是 18 个参数**（不是 14 个），少传直接 `DISP_E_PARAMNOTOPTIONAL`；
* 放样截面若**带内环**（环截面）建不出特征 → 截面只留单环，轴孔改用"−1 mm 偏置面 + 盲切 b+2 + reverse"；
* 与端面共面的草图 + `through_all` 在放样体上同样建不出，必须用上面的偏置面方案。

### v0.3.0

几何层做深一档（`sw` 192 → **199** 个工具）：

| 新能力 | 内容 | 工具 |
|---|---|---|
| 内齿轮 / 内齿圈 | 齿顶朝内的环形截面（轮缘圆 + 内侧齿形 + 拉伸，3 特征）；轮缘壁厚、四个特征圆都有判据 | `sw_internal_gear_plan`、`sw_create_internal_gear` |
| 斜齿圆柱齿轮 | 端面模数/导程/扭转角换算；**分层（lamina）近似**：每片一个偏置面 + 齿形草图 + 拉伸，片数可调 | `sw_helical_gear_plan`、`sw_create_helical_gear` |
| 矩形花键轴 | GB/T 1144，等宽直齿侧，截面精确可积 | `sw_spline_plan`、`sw_create_spline_shaft` |
| 标准键槽库 | GB/T 1096 键表（b×h、t1、t2）+ 键长系列 + 轴槽/毂槽轮廓 | `sw_keyway_lookup` |
| 渐变位齿轮 | 渐开线齿廓支持变位系数 x（齿顶/齿根/齿厚同步变化，x ∈ −0.8…1.0） | 并入 `sw_gear_involute_plan` |

真机验证（SolidWorks 33.4.1，几何读数）：

| 用例 | 判据 | 实测 | 验收 |
|---|---|---|---|
| 内齿圈 m2 z40 | 体积 28522.46（±1%） | 28522.46 mm³ | PASS 5.8 s |
| 花键轴 D46/d40 z8 | 体积 85197.301（±1%） | 85197.301 mm³ | PASS 3.1 s |
| 斜齿轮 mn2 z24 β20（4 片） | 体积 39312.8（±3%） | 39312.773 mm³ | PASS 73.7 s |
| 输出轴 333 mm（回归） | 体积 768065.6（±2%） | 768065.6 mm³ | PASS 7.1 s |

对应的负面对照也进了验收：轮缘壁厚不足、螺旋角越界、键宽超内径都必须被拒绝。

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
