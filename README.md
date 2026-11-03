# nsa-mcp-hub —— 六个 CAD/PLC 自动化内核的统一 MCP 封装

把 nxkit / gxkit / acadkit / swkit / codesyskit / autoshopkit 收进**一个内核**，
每个 kit 仍然是**独立进程**（COM 单实例、NX 冷启动、GX 抢焦点这些特性各自关在自己的进程里）。

```
                          ┌── nsa-mcp-hub-nx        （NX 2512，146 条能力）
   MCP 客户端（DSH 等）    ├── nsa-mcp-hub-acad      （AutoCAD 2025，58 条能力）
        │                 ├── nsa-mcp-hub-gx        （GX Works3，42 条能力）
        └── stdio JSON-RPC┼── nsa-mcp-hub-sw        （SolidWorks 2025，165 个工具）
                          ├── nsa-mcp-hub-codesys   （CODESYS 3.5，15 条命令）
                          └── nsa-mcp-hub-autoshop  （汇川 AutoShop V4.11，13 个工具）
```

## 快速开始

```powershell
$py = "C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = "D:\bililive\nsa-mcp-hub"
& $py -m nsa_mcp_hub.servers.sw_mcp          # 单独起一个 kit
& $py -m nsa_mcp_hub.acceptance --kit sw     # 跑验收
```

> 本机 `pip install` 必然卡死，所以 `pyproject.toml` 里的 console script 装不上，
> 一律用 `python -m` 形式运行。

## 统一返回结构

```json
{"ok": true, "kit": "sw", "capability": "sw_execute_feature_graph",
 "reads": {"...": "..."}, "checks": [{"check": "plan_steps", "got": 3, "want": ">0", "ok": true}],
 "errors": [], "seconds": 1.5}
```

**`ok` 只由 `checks` + `errors` 决定**——不看 API 返回值、不看退出码、不看 stderr。

| 判据来源 | 例子 |
|---|---|
| 原生透传 | nxkit / gxkit 的 `expect` 声明式判据 |
| 代码判据 | acadkit 每个能力自己返回的检查项 |
| 数学恒等式 | 齿轮 `da=m(z+2)`、体积 `=面积×高`、板厚比 `1.6000` |
| 结构性 | codesys / autoshop 的「后端应答 + 关键字段出现」 |

## 内核能力

| 能力 | 说明 |
|---|---|
| 单飞锁（线程） | 同一 kit 的调用串行，避免 COM 会话被打乱 |
| 单飞锁（跨进程） | `%TEMP%\nsa-mcp-hub-<kit>.lock` 文件锁，5 s 拿不到就明确拒绝 |
| 超时 + stuck 守卫 | 超时返回并记录；后续调用被挡，worker 结束后自动解除 |
| `request_id` 幂等 | 工具声明 `idempotent=True` 后，900 s 内同 id 直接回放 |
| `kit_runtime` | 每个服务器自带、**不占锁**：busy / queued / calls / stuck / 上次工具 |
| `must_have_checks` | 声明后 `checks` 为空即判负，杜绝「跑完没判据也算成功」 |
| 字段级校验 | `nsa-mcp-hub/contracts.py` + schema 轻校验，报错点名参数 |
| COM 线程初始化 | worker 线程里先 `CoInitializeEx(STA)`，否则 AutoCAD/SW 直接 `-2147221008` |

## 验收

```powershell
& $py -m nsa_mcp_hub.acceptance                          # 六家全跑
& $py -m nsa_mcp_hub.acceptance --kit sw --kit acad      # 只跑两家
& $py -m nsa_mcp_hub.acceptance --only sw.param.thickness
.\scripts\ci.ps1 -Kits sw,acad,codesys              # 单测 + 验收（带退出码）
```

**42 条用例，全部通过（42/42，714.9 s）**：

| 组 | 结果 | 说明 |
|---|---|---|
| sw | 12/12 | 特征树/参数/回滚/选面/建块/导出 STEP/索引/Sim 自检/**三段式 FEA** |
| acad | 15/15 | 线/圆/矩形/标注/文字/块/图层/3D/投影/BOM/DXF/多页 PDF |
| nx | 2/2 | 能力清单 + 真机建块（体积 100000） |
| gx | 2/2 | ST 粘贴转换（78 s）+ 全部转换（121 s，errors=0） |
| codesys | 4/4 | 服务 / 新建工程 / 工程信息 / 对象树 |
| **autoshop** | **4/4** | attach / 工程树 / 全部编译 / **写 IL→转换→编译（apply）** |

逐条明细见 **`docs/acceptance-matrix.md`**。

**跳过策略**：软件没开（SolidWorks / AutoCAD）整组 SKIP 且**不替你启动**；
AutoShop 会自动准备一份 H3U/IL 工程副本（不碰用户工程）；
单条用例有超时上限，超时判 TIMEOUT 并重启该 kit 服务器。

## autoshop `apply` 为什么能成（2026-11-02）

三条硬条件，缺一不可：

1. **工程必须是 H3U 且程序是 `MAIN.IL`**
   （`hcp --project x.hcp` 看 `DefaultEditor=1`、`FileName=MAIN.IL`；样本 `sandbox/ilcorpus`）
   —— H5U 或 `MAIN.LD` 只有梯形图，`apply` 会报 `no instruction-list editor`。
2. **跑在工程副本上**：验收 setup 复制样本到临时目录、`stop` 后 `start <hcp>`。
3. **`apply` 和 `compile` 跑完都会让 AutoShop 退出**：harness 用 `between` 钩子在用例之间自动重拉。

实测：写 84 B、97 s、`readback_ok=true`、`compile_errors=0`（只有 INT_001 的中断号警告）。

> 另注：H3U 工程的编译**不打印「统计」行**，CLI 的 `ok` 恒为 false ——
> 判据改为「没有错误行 + 确实有编译输出」。

## SolidWorks FEA（2026-11-03 已打通）

```powershell
sw_execute_feature_graph   # 建 100×50×10 方块（体积 50000）
sw_sim_setup               # 材质 AISI 304 + 底面固定 + 顶面 100 N
sw_sim_mesh --size 0.02    # 20 mm：单元 115 / 节点 264，2.7 s
sw_sim_run                 # RunAnalysis=0，0.6 s，Results 非空
sw_sim_read                # 步数 1，位移 max 5.47e-07 mm，应力 max 2102 Pa
```

**根因是单位，并非模型太大**：`CreateMesh(meshType, size, tol)` 的长度参数不是米
（传 0.02 得到 `ElementSize=0.0002 m`，差 100 倍），于是方块被划成 2134 万单元、
网格 235 s、`RunAnalysis` 跑 597 s 返回 0 但 `Results` 空 —— 这就是之前那次“求解 30 分钟没结果”。

修法三条（`mcp-patches/sw_sim.py`）：
1. `MESH_API_SCALE = 100` 做米→API 换算；
2. **单元数闸门**：超过 200 万直接拒绝并提示调大 size；
3. **求解后校验**：`RunAnalysis=0` 之后必须 `study.Results is not None`。

网格无关性：4 mm 网格位移 max 5.97e-07 mm，与 20 mm 网格的 5.47e-07 mm 差 <10%；
与解析解 δ=FL/(AE)≈1e-6 mm 同量级。

## kit-sw 的四个来源（165 个工具）

| 来源 | 数量 | 内容 |
|---|---|---|
| swkit MCP 代理 | 145 | 建模/装配/出图/钣金/导出 |
| mcp-patches 脚本 | 10 | 分步 FEA / Motion / 扫描 / DocumentMgr 索引 |
| CAD-Agent-Hub 纯算法 | 5 | 齿轮/减速器/输出轴/参数化零件/特征图编译（不需要 SW） |
| CAD-Agent-Hub 交互层 | 5 | 特征树 inspect/rollback/setparam/select + Feature Graph 执行 |

执行层默认**新建文档**，不碰已打开的文件；`sw_set_feature_parameter` 会报
`geometry_before/after/changed`，用体积与包围盒证明几何真的动了。

## 已知未完成

| 项 | 现状 |
|---|---|
| ~~分步 FEA 求解~~ | ✅ 已攻克（2026-11-03）：根因是 `CreateMesh` 长度参数差 100 倍（0.02 米 → 0.0002 米），方块被划成 2134 万单元。修好后 20 mm 网格 2.7 s 划完、0.6 s 求解、`study.Results` 非空 |
| ~~`acad.projection`~~ | ✅ 已解决（2026-11-03）：根因是**验收客户端不排空服务器 stderr**，见下方「环境坑」 |
| nx / sw / gx 覆盖面 | nx 只验了 1/146 条，sw 约 17/165，gx 3/42 |
| ~~全部已知卡顿~~ | ✅ 2026-11-03 清零：acad.projection 的 stderr 管道、分步 FEA 的网格单位、codesys 陈旧服务状态 |

## 一次“看起来像 CAD 卡死”的排查（2026-11-03）

现象：`acad.projection` 在验收里**必卡 120 s**（超时），单跑只要 9 s；而且每次都是它。

排查过程（值得记住的那几条）：

1. 单跑 / 连跑 / 同进程连跑 —— **全部 8–9 s 通过**，说明能力本身没问题；
2. 起一个旁路监视器，每秒记录 AutoCAD 主窗 enabled、`#32770` 对话框、以及**另起进程** ping COM：
   卡住的 90 秒里 AutoCAD **enabled=1、无对话框、COM 0.01 s 应答** —— 它根本没忙；
3. 往 acadkit 的 `live.run` / `finish` / `com.retry` 里加时间戳打点，发现：
   `case 结束 ok=True 7.7s` → `finish Close 完成` → **然后 110 秒空白** → 下一个用例（新进程）才开始；
4. 顺着 `live.run` 收尾往下读，最后一步是 `progress(...)` 往 **stderr** 写进度；
5. 真相：验收客户端 `McpClient` 用 `stderr=subprocess.PIPE` 起服务器，**但从没读过它**。
   acadkit 每条能力写 ~1–2 KB 进度，管道只有 ~64 KB，跑到第 12 条写满 →
   **服务器进程阻塞在 `write()` 上**，工具调用永不返回。所以受害者总是第 12 条。

修法：`McpClient` 起一个守护线程持续排空 stderr（`_drain_stderr`），尾部保留给报错用。

效果：acad 组从 **230 s（含 120 s 卡死）→ 118 s、15/15 全绿**。

顺带修掉一个真 flake：出图刚结束时 AutoCAD 会短暂拒收 COM（`RPC_E_CALL_REJECTED`），
`BACKGROUNDPLOT` 的还原/读回失败会被当成“出图失败”。acadkit `core/plot.py` 新增
`_try_busy`（忙就退避重试），还原失败不再判负。

## 工具表面（0.2.0：能力即工具）

0.2.0 之前，四个 kit 只有一个入口：`*_run_capability(ids=["geom.line"])`——模型得先查能力表
再拼 id。现在按 CAD-Agent-Hub 的形态改成**任务级工具**：

| kit | 工具 | 任务级 | 怎么来的 |
|---|---|---|---|
| sw | 174 | 170 | 原有 165 + 9 个 hub 语义增强（dirty/激活/包围盒/重建诊断/自审查/批量属性/配置/材料） |
| acad | 52 | 49 | 58 条能力 → 49 个工具（`geom.line` → `acad_geom_line`） |
| nx | 65 | 62 | 146 条能力 → 60 个（策展：建模/布尔/特征/草图/量测/装配/出图/导出） |
| gx | 46 | 43 | 42 条能力全量 |
| codesys | 59 | 56 | **77 条真服务命令**里的 56 条（旧表 17 条里有 3 条根本不存在） |
| autoshop | 41 | 40 | 24 个 CLI verb + 17 个聚焦变体（真实开关组合） |

合计 **578 个工具（任务级 559）**；经聚合网关 **579 个**（+nsa_hub_status），逐条清单见 [`docs/tool-surface.md`](docs/tool-surface.md)。

三条约定：

1. **一条执行路径**：生成的工具只调用原有的 `*_run_capability`，判据仍是能力自带的 judge，
   所以不可能出现"工具成功但几何没动"；
2. **未知参数当场报错**（不是静默忽略）：`acad_geom_line {"bogus": 1}` →
   `未知参数：bogus（该能力支持：end、start）`；
3. **`*_run_capability` 保留为逃生口**：没进策展清单的能力仍可调用，只是没有专属工具。


> **autoshop 为什么是 24 而不是 40+**：它不是"能力表"模型——AutoShop 的 CLI 只有
> 24 个 verb（`D:\bililive\autoshopkit\src\autoshopkit\cli.py`），全部已工具化。
> 再拆就只能把 `il --view/--write` 拆成两个工具这种纯包装，不增加可执行能力。
> 40+ 的门槛是为 CAD kit（58–146 条能力）定的；autoshop 按"verb 全覆盖"验收。

### 能力扫描验收（P6）

固定用例只有 42 条，能力/命令却有 285 条。因为每条能力自带 judge，可以机械展开：

```powershell
python -m nsa_mcp_hub.acceptance --kit acad --sweep            # 57 条（能力全扫）
python -m nsa_mcp_hub.acceptance --kit nx --sweep --sweep-max 20
```

扫描用例合计 **260 条**（acad 57 · nx 146 · gx 42 · codesys 15），加固定 42 条 = **302 条**。

### 取消与进度（P7）

长任务（gx 单条 120 s、autoshop `apply` 97 s、FEA 求解）以前只能等超时。现在：

```jsonc
// 客户端在 tools/call 里给 token
{"method": "tools/call", "params": {"name": "sw_sim_run", "arguments": {},
  "_meta": {"progressToken": "t1"}}}
// → 服务端每 2 s 发一条 notifications/progress（Elapsed + message）
{"method": "notifications/cancelled", "params": {"requestId": 7}}
// → 工具返回 {ok:false, cancelled:true}；脚本类工具会直接 kill 子进程
```

实测：8 s 的 `kit_sleep` 在取消后 **2.6 s** 返回（`ok=false`、`cancelled=true`），
进度通知按 2 s 到达。前提是 `tools/call` 在**独立线程**执行（否则读循环被阻塞，
取消通知读不进来）——这是内核这轮最重要的改动。

### 启动器（P8）

`_tools\nsa-mcp-hub-<kit>.cmd` 六个（不依赖 PYTHONPATH 设置），初始化返回
`{"name": "nsa-mcp-hub-sw", "version": "0.2.0"}`。


### 内核 0.2.0 的两个硬约束（2026-11-03 实测，踩过两次）

1. **子进程绝不能继承 MCP 的 stdin**。JSON-RPC 管道被 AutoCAD / run_journal(NX) /
   autoshop CLI 继承后，调用会卡到超时（实测：nx 直跑 16 s，经 MCP 300 s 超时；
   栈显示卡在 `communicate()`）。修法是每处 spawn 都 `stdin=subprocess.DEVNULL`
   （acadkit `launch`、nxkit `session.run`、gxkit `session.start`、autoshop `_run`）。
2. **重依赖不能在工具调用线程里首次 import**。ezdxf 在"stdout 被重定向 + COM 已初始化
   + 读线程在跑"的上下文里首次 import 会**死锁**（faulthandler 显示停在
   `ezdxf/lldxf/validator.py`）；DXF 判据因此卡 45 s+。修法：服务器启动时预热
   `import ezdxf`。

排查手段（都留着，env 开关）：`NSA_MCP_HUB_DUMP_STACKS=10`（周期性打线程栈）、
acadkit 的 `progress.txt`（每个用例阶段落盘）、`NSA_MCP_HUB_SYNC_TOOL_CALL` 已废弃。



## 从 CAD-Agent-Hub 补进来的两块（2026-11-04）

CAD-Agent-Hub 里 nsa-mcp-hub 原本没有的能力，按"能不能代理就别重写"的原则接进来：

| kit | 工具 | 覆盖 | 状态 |
|---|---|---|---|
| **ug** | 83（82 + 1 诊断） | **NX CAM** 16（刀路/后处理/CLSF/MCS/毛坯）、**机床与运动学** 20（整机、限位、碰撞停止、静态间隙）、**NX 钣金** 6（tab/flange/bend/展开图/DXF）、装配约束写入 2、制图注释、交换格式导入、`run_python` | 需要 NX 交互式会话 + `nx_user/startup` 的 `NXMcPRemotingServer.dll`，并在 NX 里跑过 `start_mcp.py` 起 socket 桥；桥没起时如实报错 |
| **catia** | 56（55 + 1 诊断） | CATIA V5 建模（pad/pocket/fillet）、曲面（loft/fill/join/heal/thick/boundary/close）、**原生 Analysis**（建分析文档→set/entity/mesh/solution→材料→计算→报告/导数据/截图） | **本机未安装 CATIA**，验收 SKIP；工具面已接进网关，装上即可用 |

另有三块本机没有软件、只作为资产收在 `_contrib/`（见该目录的 README）：
`ansys-structural-workbench`（ANSYS 结构分析 skill，带质量门禁）、
Fusion 360 的本地写入桥与 Starship v3 参数化建模示例、build123d/cadpy 模型样例。

SolidWorks 侧同时补齐了上游有、我们缺的两个工具：`sw_reload_runtime`（SW 重启/崩溃后重连 COM，
只做附着、不会顺手启动 SW）与 `sw_operation_status`（COM 连接 + 文档数/脏文档数，SW 关着也能答）。

## 聚合网关：nsa-mcp-hub

六个 kit 各是一个 MCP 服务器（各自独占 COM/UI 与崩溃域）。**日常用网关就够了**：

```powershell
D:\bililive\DeepHarness\_tools\nsa-mcp-hub.cmd     # 或 D:\bililive\nsa-mcp-hub\_tools\nsa-mcp-hub.cmd
```

* `tools/list` → **579 个工具**（八家合计，去重后）；`initialize` 返回
  `{"name": "nsa-mcp-hub", "version": "0.2.0"}`；
* 路由：工具名前缀 `sw_/acad_/nx_/gx_/codesys_/autoshop_` 决定转发给哪个子进程；
  没有前缀的老工具（`swdm_stats`/`swdm_query`）走"工具名→kit"索引，也能路由；
* 每个 kit 自带的状态工具 `kit_runtime` 在聚合层被 `nsa_hub_status` 取代
  （一次看八个 kit 的存活/工具数/pid/最近错误/stderr 尾巴）；
* `notifications/progress` 与 `notifications/cancelled` 都会**透传**给对应子进程；
* 子进程 lazy 启动（第一次需要时才起），hub 退出时一起收掉；子进程 stderr 由排空线程接住。

DSH 里已经改成只挂这一条（`%USERPROFILE%\.dsh\cordis.patch.yml`），
原来的六条 `nsa-mcp-hub-*` 已摘掉；回退办法：同目录下 `cordis.patch.yml.bak-hub-*` 覆盖回去再重启 DSH。
六个单独的 `.cmd` 启动器仍保留在 `D:\bililive\DeepHarness\_tools\`，随时可以单挂。

## 环境坑（都踩过）

- **`contextlib.redirect_stdout` 是进程全局的**：worker 超时后它还在跑，会把后续所有
  协议响应写进 stderr → 客户端永久卡死。修法：`jsonrpc._write` 绑启动时的真实 stdout。
- **AutoCAD `ATTDIA=1`** 会让块属性插入弹框卡死；验收前 `SetVariable("ATTDIA", 0)`。
- **AutoCAD close/reopen 判据**会撞「是否保存」提示；用例之间 `doc.Save()` 消掉。
- **pywin32 拿不到 `SelectionManager.CreateSelectData`**（`-2147352573`）；改用 `entity.Select2`。
- **`EditRebuild3` 返回 True 但几何不更新**；要 `ForceRebuild3(False)` 才当场重算。
- **`GetActiveObject("SldWorks.Application")` 不可用**（不在 ROT），要 `Dispatch`。
- **AutoShop 的 `view_il`(32883) 在本机是「连接 PLC」**，不是切指令表；靠 `MAIN.IL` 工程绕开。
- 测试脚本输出被缓冲时看不到进度：用 `python -u` 或 `flush=True`。
- **CODESYS 的 `service.json` 存在 ≠ 服务活着**：CODESYS 关掉后旧端口还在文件里，
  验收 setup 直接复用就会 4 条全报 `WinError 10061 积极拒绝`。修法：setup 先 TCP connect 一次，
  连不上就把 state 归档成 `.stale` 再重启服务。
- **`stderr=subprocess.PIPE` 必须有人读**：不读就写满 ~64 KB 缓冲区，子进程阻塞在 `write()`，
  表现成“某个工具调用永不返回”，而且往往是跑到固定第 N 条才出现。
- PowerShell 里别写 `Get-Content $p -LiteralPath $p`（位置参数），会把文件读成空再覆盖掉。
