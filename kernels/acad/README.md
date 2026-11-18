# acadkit — 我自己的 AutoCAD 自动化内核

> **NSA = Non-standard automation（非标自动化）** —— 仓库名与 `nsa_*` 工具前缀都取自这个缩写。
> 本仓是这套工具链的一员：目标是**让做非标自动化设备设计的工程师，能更方便地驱动手边这些软件**，
> 把重复的建模、出图、编号、编程动作交给 agent，精力留在方案、机构与判断上。

> 不是"又一层 MCP 包装"，而是**带判据的工具内核**：每条宣称可用的能力，
> 都在 `docs/registry.yaml` 登记了真实 API、实测证据，以及——同样重要的——
> **哪些根本用不了、为什么**。

一个仓库，三个入口，同一套能力：

| 入口 | 用法 | 面向 |
|---|---|---|
| Python 库 | `from acadkit import caps; caps.get("geom.circle")` | 写脚本、二次开发 |
| CLI | `acadkit run --only geom` / `acadkit cap dim.linear --param expected=80` | 手动跑、批处理、排查 |
| MCP server | `acadkit-mcp`（stdio） | 任意 MCP 客户端（Claude / DSH / 编辑器） |

设计原则一句话：**能力 = 动作 + 判据 + 真机用例 + 文档**。四件套缺一，不许标
`verified`。

## 为什么不是直接包一层 ActiveX

上游那些"工具清单"式实现，实测下来有一批**看着能用、其实不能**：

- `Solid3D.Boolean(1, other)` 并集把 12000 算成 **4000**（应 10000），
  `Boolean(3, …)` 直接报"参数 Operation 无效"；
- `PlotToFile` 返回 True，文件 **0 字节**（`BACKGROUNDPLOT=2` 的锅）；
- `MLeader.TextString` 赋值不报错、读回**空串**；
- `-LAYERSTATE` 只要动过图层表就**永久卡在命令提示符**；
- `ACDBTABLE` 第 0 行是合并标题行，往里写的东西**落盘就没了**。

这些不是"参数没调对"，所以本仓库的做法是：**动作按实测配方重写，判据一律
从 AutoCAD 读回**（计数/面积/体积/句柄/文件签名），并把结论写进
[`docs/PITFALLS.md`](docs/PITFALLS.md) 与 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md)。

## 一条命令跑通

```bash
python tests/run_all.py          # 离线 87 条 + 文档一致性 + 真机 58 条（约 7–9 分钟）
python tests/run_all.py --skip-live
```

真机套件会自己用 `acad.exe /p "<<VANILLA>>"` 起 AutoCAD，逐条跑
"建图 → 读回 → 存盘重开 → 判据 → 环境自检"，跑完 `clean_quit`（进程消失、
不留 `.sv$`）。

<!-- gen:counts:BEGIN -->
| 指标 | 数字 |
|---|---|
| registry 能力总数 | 67 |
| verified（有判据、真机通过） | 62 |
| usable_unjudged | 0 |
| pending | 0 |
| dead（本机无官方路径） | 5 |
| external（外部资产 / 未移植） | 0 |
| 内核实现能力（`caps`） | 64 |
| caps 覆盖的 registry id | 62 / 67 |
| 真机用例 | 64 条（含负例 2 条） |
<!-- gen:counts:END -->

## 快速开始

```powershell
pip install -e ".[dxf,mcp]"      # Windows + 已装 AutoCAD 2025（完整版）

acadkit selftest                 # 离线自检（registry / caps / 判据）
acadkit status                   # 环境自检（只附加，不启动 AutoCAD）
acadkit list                     # 能做什么（族 / 级别 / 状态）
acadkit run --only geom,dim      # 真机跑两族
acadkit-mcp                      # MCP（stdio）
```

MCP 客户端注册示例：

```json
{ "mcpServers": { "acadkit": { "command": "acadkit-mcp", "args": [] } } }
```

## 判据：四级，缺一不可

来自 [`docs/JUDGE_SPEC.md`](docs/JUDGE_SPEC.md)：

| 级别 | 内容 | 例子 |
|---|---|---|
| L1 | 计数：目标表/类型的数量按预期变化 | 圆 +1 |
| L2 | 属性读回：关键字段与输入一致 | `Radius=25`、`Measurement=60` |
| L3 | 几何自洽：用解析值交叉验证 | `Area≈πR²`、`Volume=12000`、`pdf 页数=1` |
| L4 | 存盘重开：DWG 重开后按句柄再读一遍 | 属性仍一致、计数仍一致 |

硬规矩（代码里强制）：

1. `ok` 只在 `judges.base.verdict()` 里由 `all(checks.values())` 算出；
   `checks` 含 `None` 或空集直接抛 `JudgeError`；
2. `detail` 必须有能人工核对的数字；
3. 每条用例**前后各一次**环境自检（profile / 系统变量 / 文档数 / `.sv$` /
   进程 / 单实例 / 有没有弹模态 / 出图后变量还原）；
4. 判据是纯函数（吃 `Readback`，不碰 COM），所以同一份代码能用离线构造的
   读回值证明"它真的会失败"。

## 架构

```
src/acadkit/
├─ registry.py    docs/registry.yaml 载入（无 PyYAML 也能跑）
├─ caps.py        能力表：id → 动作(build/) + 判据(judges/) + 默认参数 + 级别
├─ live.py        真机执行层（起 CAD / 跑一条或一组 / 收尾 / 看门狗）
├─ build/         怎么画：参数化动作（geom/text/dim/gdt/symbol/table/block/
│                 frame/layer/envvars/solid/boolean/view/lisp/export）
├─ judges/        怎么证明：base(verdict/Readback) + read(COM 读回) +
│                 generic(实体/计数/命名表/体积) + 各族专用判据
├─ core/          COM 桥（忙重试/代理刷新/干净退出）+ 启动 + 出图
├─ cli/main.py    status / env-* / registry / list / cap / run / judges / selftest
└─ mcp/server.py  MCP：status / list_caps / registry / run_caps
```

`tests/live_judges.py` 是 `live.py` 的薄壳；`tests/test_judges.py` 是判据的离线
测试（正例 + **每条判据都必须能失败**）；`tests/test_docs.py` 防文档漂移。

## 实测记录

- [`docs/PITFALLS.md`](docs/PITFALLS.md) —— 12 类"看着能用其实不能用"的坑；
- [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md) —— dead / external 两张表；
- [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) —— 全部能力（自动生成）；
- [`docs/PARITY.md`](docs/PARITY.md) —— 覆盖率四个口径 + 按受众就绪度（自动生成）；
- [`docs/BACKLOG.md`](docs/BACKLOG.md) —— **挖掘全量清单**：还能挖什么、总量多少、明确不做（自动生成）；
- [`docs/CADCRAFT_MINE.md`](docs/CADCRAFT_MINE.md) —— **从 CADCraft 能吸收什么**：40 项 / 325h，按移植/规格/参考分类（自动生成）；
- [`docs/GAPS.md`](docs/GAPS.md) —— 缺口账本：影响分、工时、解锁条件（自动生成）；
- [`docs/ALPHA_GATE.md`](docs/ALPHA_GATE.md) —— 5 条端到端工作流真机结果；
- [`docs/registry.yaml`](docs/registry.yaml) —— 唯一事实来源；
- [`docs/P1_PROGRESS.md`](docs/P1_PROGRESS.md) —— 分步真机验证记录。

### 进程内通道（.NET 插件）

ActiveX/命令行够不着的能力（`solid.revolve` / `layer.state`，以及待实现的
`dim.associative` / `block.edit_inplace`）走 [`dotnet/`](dotnet/README.md)：
一个 `net8.0-windows` 插件，命令结果写成图面 `AKRESULT <TAG>: ...`，判据仍走读回。

```bash
python dotnet/build.py            # 构建
python tools/netload.py --deploy  # 装到 AutoCAD 安装目录 + 写注册表（先关 AutoCAD）
python tools/netload.py           # 启动并验收 4 条命令
```

**NETLOAD 不能用**（弹模态对话框，SendCommand 挂死）；`SECURELOAD=1` 也要求
DLL 在信任路径。细节与三条路的实测结论见 [`dotnet/README.md`](dotnet/README.md)。

## 已知边界

- **标注是非关联的**（`dim.associative` 为 dead）：ActiveX 建的标注不与几何关联，
  `IAcadDimension` 也没有 assoc API；六种命令行输入（点选/选对象/预选/OSNAP+REGEN/
  DIMREASSOCIATE）要么卡在提示符，要么 `Measurement` 不跟随。唯一路线是
  NETLOAD 一个 .NET 插件用 `DimensionAssociation`（进程内），不在 COM 内核范围。
- **表格第 0 行是合并标题行**：往它第 1..n 列写文字落盘即丢；中文单元格另需
  `SetCellTextStyle` 挂 TrueType 样式（`table.chinese` 已验证）。
- **旋转体**（`solid.revolve`）、**命名图层状态**（`layer.state`）本机不可用；
  见 [`UNSUPPORTED.md`](docs/UNSUPPORTED.md)。
- **Electrical / PLC 能力要本机有 AeData**（`~/Documents/Acade 2025/AeData`）：
  `ae.db` / `plc.build` 只读那 7 个库和 `ace_plc.mdb`，不启动 ACADE；
  没装 Electrical 元件库时这两条会失败并给出原因。
- **多页 PDF 用合并**：ActiveX `SetLayoutsToPlot` 产不出多页文件（实测），
  `export.pdf_multipage` = 逐布局出图 + `pypdf` 合并（`pip install acadkit[pdf]`）。

## 开发

```bash
python scripts/doctor.py            # 换机器自检（远端/SSH/pywin32/AutoCAD/profile）
python scripts/install_hooks.py     # 装 pre-push（拿不到 SSH 或文档过期就拒推）
python tools/gen_readme_counts.py   # 重新生成 README 计数 + CAPABILITIES.md
python tools/gen_unsupported.py     # 重新生成 UNSUPPORTED.md
```

加能力的标准流程见 [`docs/RECIPES.md`](docs/RECIPES.md)，
给 agent 的第一页是 [`AGENTS.md`](AGENTS.md)。

## 许可

MIT（[`LICENSE`](LICENSE)）。第三方依赖与商标说明见 [`NOTICE.md`](NOTICE.md)。
本仓库不隶属于 Autodesk。
