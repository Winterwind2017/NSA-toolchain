# nsa-mcp-hub

把多个 CAD / PLC 自动化内核统一成 **一个 MCP 端点**，并且**用判据（checks）决定成败**，而不是用“调用没报错”决定成败。

这个仓库是我在日常非标自动化设计、出图、PLC 编程中沉淀下来的一层基础设施：每个软件背后是一套独立内核（AutoCAD、SolidWorks、NX、GX Works3、CODESYS、汇川 AutoShop、CATIA、EPLAN），hub 负责把它们接成统一的工具面、统一的返回结构、统一的验收口径。

## NSA 是什么

**NSA = Non-standard automation，也就是「非标自动化」。**

这个缩写是整条工具链的名字来源：`nsa-mcp-hub` / `nsa_mcp_hub` 的包名、`nsa_*` 的工具前缀、
仓库名都取自它。目的很直接——

> **让做非标自动化设备设计的工程师，能更方便地驱动手边这些软件。**

AutoCAD、SolidWorks、NX、EPLAN、CODESYS、GX Works3、汇川 AutoShop、CATIA 各有一套自己的
对象模型和一堆坑；非标设计又天生是"一次一版、边做边改"，重复的建模、出图、编号、编程动作吃掉的时间
远比想象的多。这套工具把这些动作交给 agent，设计人员把精力留在方案、机构与判断上。

也正因为面向的是**要交付的图纸与程序**（不是演示），这里的每个工具都不满足于"能调通 API"：
建模要读回体积与特征数，出图要读回注释文本和表格单元格，PLC 要有编译诊断与行号定位——
**非标项目里最贵的成本是"改错一次"**，所以判据优先于功能数量。

## 仓库可见性

**本仓库是私有（private）仓库。** 文档里的「发布 vX.Y.Z」指的是**打 git tag + 推 main 分支**，
不是把仓库转成公开；仓库可见性不随发版变化。

想复核可以跑：

```bash
python scripts/assert_private_repos.py                        # 检查账号下全部仓库
python scripts/assert_private_repos.py --only nsa-mcp-hub     # 只查本仓库
```

脚本用 `gh` 读 `isPrivate`，只要有一个仓库不是私有就 **退出码 1** 并逐条列出——
把“我以为它是私有的”变成一条可执行断言。

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
| `sw` | swkit | SolidWorks 2025 | 子 MCP + hub 侧脚本/特征层 | 204 |
| `acad` | acadkit | AutoCAD 2025 | 进程内（COM） | 55 |
| `nx` | nxkit | NX 2512 | 进程内（`run_journal` 批处理） | 66 |
| `ug` | NX 扩展服务 | NX 2512 | proxy（.NET remoting 挂活会话） | 88 |
| `gx` | gxkit | GX Works3 | 进程内（UIA + 前台窗口） | 47 |
| `codesys` | codesyskit | CODESYS 3.5 | 进程内（常驻服务） | 60 |
| `autoshop` | autoshopkit | AutoShop V4.11 | 进程内（UIA / frida） | 42 |
| `catia` | CATIA 服务 | CATIA V5 | proxy | 56 |
| `eplan` | EPLAN 服务 | EPLAN 2.9 | proxy | 16 |

合计约 635 个工具。数量随宿主软件版本、是否在线、以及本机内核版本浮动；工具名一律带 kit 前缀（`sw_`、`acad_`、`ug_` …），便于路由。

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

### v0.15.2

补一段命名说明：**NSA = Non-standard automation（非标自动化）**，并说明这套工具的目标是让
非标自动化设备设计人员更方便地驱动 AutoCAD / SolidWorks / NX / EPLAN / CODESYS / GX Works3 /
AutoShop / CATIA。功能无变化。

### v0.15.1

只加一条护栏：把「私有仓库」与「发布 = 打 tag」写进 README，并新增
`scripts/assert_private_repos.py`——用 `gh` 读 `isPrivate`，任一仓库非私有即退出码 1。
本轮实测：账号下 **22 个仓库全部私有**，`nsa-mcp-hub` / `solidworks-agent-kit` 均为 `PRIVATE`。

### v0.15.0

BOM 的"代号"列有了真正的命名规则，名称列改中文，备注列带参数。

| 改动 | 内容 |
|---|---|
| 代号规则 | `code_rule` 三档：**`drawing_number`（默认，首选）** 装配图号 + 序号 → `NSA-ASM-0001-01…-07`；**`type_code`（次选）** 按零件类型编码 → 齿轮 `G<模数>x<齿数>-序号`（`G2x20-01`）、轴 `S<直径>-序号`（`S9.8-05`）；`filename` 用文件名 |
| 中文名称 | 一级小齿轮 / 一级大齿轮 / 二级小齿轮 / 二级大齿轮 / 输入轴 / 中间轴 / 输出轴 |
| 备注列 | 齿轮 `m=2 z=20`；轴 `φ9.8×33` |
| 结构 | 零件改带元数据（kind/name/teeth/diameter/remark），BOM 行直接由元数据生成，代号与名称同源，不会串行 |

实测（两种规则各跑一遍，都是 6.2 s 左右、判据全过）：

| 规则 | 代号 |
|---|---|
| `drawing_number` | `NSA-ASM-0001-01 … NSA-ASM-0001-07` |
| `type_code` | `G2x20-01, G2x40-02, G2x20-03, G2x60-04, S9.8-05, S11.8-06, S13.8-07` |

表格仍是 **8 行 × 6 列 / 42 格 / 7 项读回**，标题栏 5 栏，国标 A3 图框。

### v0.14.0

装配图换成**国标 A3 图框**，BOM 表做成能看的六列表格，标题栏栏位真的填上字。

| 改动 | 内容 |
|---|---|
| 国标图框 | 图纸改用本机的 `gb_a3.drwdot`（GB/T 14689 A3 幅面，图框 + 图纸格式自带 GB/T 10609.1 标题栏，实测 82 条注释），`sheet_size` 可选 a0–a4 |
| BOM 表 | 六列设计：**序号 / 代号 / 名称 / 数量 / 材料 / 备注**，列宽 10/42/52/12/22/32 mm，表头写在第 0 行并设行高，数据 7 行逐格写入、逐格读回 |
| 标题栏 | 模板的标题栏是静态格子 + 一批**空白注释**；按坐标找出空白栏位（21 个），把 图样名称/图号/材料/比例/单位 落进去，判据是**落点自己的文本读回** |
| 装配视图尺寸 | 单实体尺寸扫描，目标为轴长/齿宽/孔径，命中即真尺寸，未命中给参考尺寸（本轮三项都走了参考尺寸） |

实测（国标 A3 减速器装配图，4.6 s）：

| 项 | 结果 |
|---|---|
| BOM 表 | **8 行 × 6 列**，列标题 `序号/代号/名称/数量/材料/备注`，**42 格写入**，7 个零件名全在 |
| 标题栏 | 空白栏位 21 个，**5 栏填充并读回一致**（名称 / 图号 / 材料 45 / 比例 1:2 / 单位 NSA） |
| 图纸注释 | 74 条（国标标题栏与图框都在） |
| 尺寸 | 3 项覆盖（轴长 33 / 齿宽 10 / 孔径 10，均以参考尺寸标注） |
| 组件 | 7 |

### v0.13.0

上一版判定"SW 表格 API 不可用"是**错的**——生成早期绑定后三件事全通了。

| 改动 | 内容 |
|---|---|
| 表格真相 | `InsertTableAnnotation2` 的真实签名是 **7 参**：`(UseAnchorPoint, X, Y, AnchorType, TableTemplate, Rows, Columns)`。之前只传 4 参，所以恒定报「类型不匹配 参数4」。补上参数后**原生表格**直接建成 |
| 单元格 | `ITableAnnotation.SetText` 在**动态绑定下不可见**，必须用 makepy 生成的早期绑定接口包一层（`mod.ITableAnnotation(table._oleobj_)`）；没有绑定就按需现场生成一次 |
| 球标 | `SelectByID2` 的 callout 必须是 `VARIANT(VT_DISPATCH, None)`，选中视图后 `AutoBalloon2(1, True)` 返回**球标数组**——原生球标成立 |
| BOM 表 | SW 自己的 BOM 仍只枚举 1 行（BomType 1/2/3 都一样），但现在不影响交付：明细走**原生表格** |

实测（减速器装配图，3.0 s）：

| 项 | 结果 |
|---|---|
| 原生表格 | `kind=sw_table`，**9 行 × 4 列**（SW 自带表头），**32 格写入** |
| 零件名读回 | **7/7**（逐格读回核对） |
| 球标 | `kind=sw_balloon`，`added=1`（原生） |
| 组件 | 7 |

怎么拿到这些签名的：对 `sldworks.tlb` 跑 `python -m win32com.client.makepy`，生成
`{83A33D31-27C5-11CE-BFD4-00400513BB57} v33`，然后直接读生成文件里的 `def InsertTableAnnotation2(...)`。
附带结论：`gencache.EnsureDispatch("SldWorks.Application")` 仍然拒绝（coclass 没登记 typelib），
但**把已有对象包进生成的接口**（`mod.IDrawingDoc(doc._oleobj_)`）是完全可行的。

### v0.12.0

检验图的尺寸终于有了工程含义。

| 改动 | 内容 |
|---|---|
| 单实体尺寸 | 改用**单实体**加尺寸：圆边得到直径/半径、直线边得到长度——不会再退化成角度尺寸（那需要两条不平行的边） |
| 目标匹配 | 按几何真值（齿顶/分度/齿根/外径/内径）在实体里搜索，命中即保留真尺寸并记下 `value_mm` 与命中实体序号 |
| 参考尺寸 | 轮廓是多段线的目标（齿轮外径、分度圆）**无法**加 φ 尺寸——工程上按**参考尺寸**写，工具会自动补 `φ44`、`φ40` 这样的参考标注并读回 |

为什么外径标不出来（这轮查清的事实）：本机齿轮轮廓是**逐齿多段线**，每个齿由若干小线段/小圆弧组成，外径根本不是一条圆边；
只有轴孔那种真圆才能加 φ 尺寸。所以正确做法是"能测的标真尺寸、轮廓标参考尺寸"，而不是硬凑一个 φ。

实测（m2 z20 齿轮图）：

| 项 | 结果 |
|---|---|
| 真尺寸 | **齿根半径 17.5 mm**（实体 #37，`kind=radius`，正好等于 rf = 17.5） |
| 参考尺寸 | **φ44**（齿顶）、**φ40**（分度圆） |
| 扫描实体 | 60 个 |
| 耗时 | 14.3 s |

### v0.11.0

装配图的 BOM 真正展开成 8 行表格，球标也有了；检验图的尺寸读数改成如实上报。

| 改动 | 内容 |
|---|---|
| BOM 表 | 从"一句明细注释"换成 **8 行 × 4 列表格**（序号/零件名称/数量/材料），32 格逐格写入并逐格读回；判据 = 行数 8、格数 32、7 个零件名全在表里 |
| 球标 | 先试 SW 的 `AutoBalloon2`；它依赖 BOM 项号，本机不生效时**退化为带圈件号注释**（①②③…），并把实际用的是哪一种如实写进 `reads.balloons.kind` |
| 尺寸读数 | 视图尺寸现在会读出**数值**：`IDisplayDimension.GetDimension2(0).GetSystemValue2("")`（系统单位米/弧度），线性折算 mm、角度如实给弧度 |

**为什么表格是"注释网格"而不是 SW 表格对象**：`InsertTableAnnotation2/InsertTableAnnotation` 在本机（pywin32 动态绑定）恒定报
`com_error -2147352571 类型不匹配 参数4`，`gencache.EnsureDispatch("SldWorks.Application")` 也直接拒绝
（`This COM object can not automate the makepy process`）。所以表格用逐格注释摆出来：视觉上是表、能逐格读回，
`reads.bom_table.kind` 会写 `note_grid`，不冒充 SW 原生表。

同样如实说明的一条：视图尺寸目前是**自动配对实体**得到的，本机实测配对结果是两个**角度尺寸**（3.11 / 3.08 rad），
`reads.dimension_values` 会写明；有工程含义的 φ/齿宽尺寸需要先按实体类型挑边（下一步）。

实测：

| 用例 | 结果 |
|---|---|
| 减速器整机装配图 | PASS 2.7 s，7 组件、BOM 表 **8 行×4 列 / 32 格 / 7 项**、球标（圈号注释）、标题栏 |
| 齿轮检验图 | PASS 5.2 s，2 个角度尺寸（读数已报） |
| 花键检验图 | PASS 2.7 s |

### v0.10.0

检验图从"注释"升级成"带尺寸的图"，并补上整机装配图 + BOM。

| 改动 | 内容 |
|---|---|
| 视图尺寸 | 检验图现在会**在视图里选实体 → `AddDimension2`**，把尺寸真正附着到视图上；判据是 `IView.GetDisplayDimensions` 计数增加（实测 **+2**） |
| 整机装配图 | 新工具 `sw_reducer_assembly_drawing`：现建（或复用已落盘的）**4 个齿轮 + 3 根轴** → 装配 **7 组件** → 图纸前视/等轴测 → **BOM 表** + 明细注释 + 标题栏 |
| 零件落盘 | 修掉 `save_path` 的老问题：`SaveAs4` 的 `Errors/Warnings` 是 byref VARIANT，传 `None` 报「类型不匹配」，改成先 `SaveAs` 再退回 `SaveAs4`——现在 `sw_create_*(save_path=...)` 真的会写盘 |

实测：

| 用例 | 结果 |
|---|---|
| 齿轮检验图 | PASS 0.9 s，视图 `*前视`+`*上视`，**新增 2 个视图尺寸**，注释 179 / 标题栏 70 字符 |
| 花键检验图 | PASS 3.1 s |
| 减速器整机装配图 | PASS 2.1 s，**7 组件 / BOM 表 / 明细 8 行（表头 + 7 项）/ 标题栏** |

关于 BOM 行数：本机 `InsertBomTable2` 的 `BomType=1`（仅顶层）只给 1 行，`2`（仅零件）给 1 行且不展开——所以判据不押在 SW 的 BOM 枚举上，而是**另写一条可读回的明细注释**，把 7 个零件名逐个核对。

### v0.9.0

把检验这条线补成"一张图 + 一张整机表"，并把花键的量柱规则讲清楚。

| 改动 | 内容 |
|---|---|
| 检验图 | 新工具 `sw_inspection_drawing`：零件另存 → 新建工程图 → 放**前视/上视** → 写检验注释 + 标题栏（图号/材料/比例/日期）。没有现成零件时按 `kind` **现建一个**（`auto_part`）。判据：视图数 ≥1、注释读回含关键数值、标题栏读回含图号 |
| 花键量柱 | 规则显式化：**在齿侧接触的分支上**让量柱中心落在**径向中径**；报告给出 `pin_diameter_rule`、`pin_contact_radius_mm`、`mid_tooth_height_radius_mm`、`contact`；另给 `flank_transition_pin`（落底→夹住的临界量柱） |
| 减速器整机表 | `sw_inspection_note(kind="reducer")` 一条注释装下 **4 个齿轮的 W/M + 3 处键槽的 b×h/t1/t2/键长**（9 行），可只格式化也可写进工程图 |

实测：

| 用例 | 结果 |
|---|---|
| 齿轮检验图（现建齿轮 → 图 → 视图 → 注释 + 标题栏） | PASS 10.2 s，视图 `*前视` + `*上视`，注释读回 179 字符、标题栏 70 字符 |
| 花键检验图 | PASS 6.6 s |
| 减速器整机检验表（写图） | PASS 0.5 s，9 行，读回含跨棒距与键宽 |
| 花键量柱规则 | 量柱 Ø8.455、中心 21.4995 ≈ 中径 21.5、`contact=flank` |

两个真机坑（本机）：`SaveAs4` 的 `Errors/Warnings` 是 **byref VARIANT**，传 `None` 直接「类型不匹配」——改用 `SaveAs`；工程图视图名**只认本地化**（`*Front` 返回 None，`*前视` 才建得出来）。

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
