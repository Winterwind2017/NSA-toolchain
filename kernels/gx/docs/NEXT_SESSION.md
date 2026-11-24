# 下次接续：还没开发的方向（收口于 2026-10-25，v0.16 / 42 条能力）

> **给下一次开工会话的自己看**：这份是交接单。用户说「连上真机了 / 继续做剩下的」时，
> 先读完这一页再动手，不要重新摸一遍。
>
> 当前基线：`gxkit 0.16.0`，**42 条能力，三轮全绿**（6302.2 / 6327.1 / 乱序 seed=47 6302.8 s），
> 内核 `f4b4263`、技能 `081f417`，均已推。GX Works3 没有 COM/API，全部靠 Win32 消息 +
> 真鼠标键盘，判据一律从 `.gx3` 读回。

## 0. 开场三步（不需要用户额外交代）

```powershell
cd <repo>\gxkit
$py = "python"
$env:PYTHONPATH='<repo>\gxkit\src'
& $py -m gxkit selftest          # 期望：自检通过：42 条能力
& $py -m pytest -q tests         # 期望：34 passed
& $py tools\check_consistency.py # 期望：五处数字一致
```

之后按「改一批 → 单跑该项 → 全量三轮」推进（用户已确认能接受每轮约 105 分钟）：

```powershell
& $py -m gxkit run --workdir <repo>\gxkit\_runs\a1
& $py -m gxkit run --workdir <repo>\gxkit\_runs\a2
& $py -m gxkit run --shuffle --seed 61 --workdir <repo>\gxkit\_runs\a3
```

## 1. 能纯离线继续做的（不需要真机）

按性价比排序。每条都写了**现状 / 证据 / 下一步第一个动作**。

### ① SFC 正文 —— 最有希望（估 3–5 h）
- **现状**：只能建 SFC 工程（`project.new_language` 的 lang=2，标题 `[SFC]`），画不了内容。
- **证据**：SFC 工程里正文 DB 是 `*_SFCDB.db`（不是 LDDB）；IEC XML 的 SFC 正文被静默丢弃（探针 123）。
- **下一步**：新建 lang=2 工程 → 用 SFC 编辑器画「初始步 + 转移」→ 存盘 → `sqlite3` dump `SFCDB` 的表名/列/行，
  看是不是和 LAD 一样的文本 DSL（LAD 是 `LadderBlocks(id,pos,blocktype,data,...)` + `V1:` DSL）。
  若同构，`src/gxkit/ladder.py` 的解析思路可直接复用，另写 `sfc.py`。

### ② FBD 正文（估 3–5 h）
- **现状**：只能建 FBD 工程（lang=3，标题 `[FBD/LD]`）；正文 DB 是 `*_FBDDB.db`。
- **下一步**：同上，画一个「AND 块 → 输出」，dump `FBDDB` 看编码。

### ③ LAD 写到「非默认程序」（估 1–2 h）
- **现状**：`program.write_ladder*` 只作用于**当前打开的程序**（默认 `ProgPou`）。
- **卡点**：要在指定程序里画，得先把它切到前台；`uia.open_program` 能开但**不稳定**（见 §3）。
- **替代思路**：`program.multi_programs` 已能建多程序。可以先建好、让目标程序成为默认打开的那个，
  或先在默认程序画完再"改名/复制"——具体哪条可行要试。

### ④ 软元件注释写入（估 1–3 h）
- **现状**：只读（`inspect.devices` 读 `*_DC.db` 的 `DEVICE_DATA`，FX5U 2935 行）。
- **下一步**：先看 `DEVICE_DATA` 里注释列是明文还是编码；GUI 侧的「软元件注释」表可作第二条路。

### ⑤ 标签导入的 WORD/DINT（估 0.5–1 h）
- **现状**：`label.import_xml` 只验证过 BOOL（`label.multi_type` 覆盖 BOOL/WORD/DWORD 三种，
  但那是**标签**；`<Variable>` 的非 BOOL 初值规则此前踩过坑）。

### ⑥ QCPU 的机架/模块配置（估 1–2 h，可能是死路）
- **现状**：新建对话框选 `QCPU`（series=4）后**机型下拉为空**（probe141），说明需要先配机架。
- **下一步**：在对话框里找"机架/模块"入口；若无，判定该系列不可用并写进 `UNSUPPORTED.md`。

### ⑦ 工程校验结果表的全部行（估 0.5–1 h）
- **现状**：`project.check` 能校验，但结果页 DataGrid **只暴露 1 行**（虚拟化），
  所以判据用的是状态行 `存在N个不同内容`。
- **下一步**：试滚动后重新 FindAll（行会随滚动进/出 UIA 树），或找"导出至文件"。

### ⑧ 导航树改写已有程序（估 2–3 h，已知不稳定）
- 三个真因已定位（见 §3），要做得先把这套组合拳打到稳定：先 `activate_pane_tab(pid,"导航")`
  → 最大化 → 重读行矩形 → ±20px 扫点 → 用标题里的 `[ST]` 验证。

## 2. 需要真机（真实 PLC 或 GX Simulator3）才能做的

这些在离线口径下已明确排除，等用户接上 PLC 再说。菜单入口已知：
`在线(O)`、`调试(B)`；`转换(C)` 里有 `转换+RUN中写入(O) Shift+F4`。

1. **在线监视**：梯形图/软元件监视（读当前值、时序图）。
2. **写入 PLC**：全量写入 / RUN 中写入（Shift+F4）/ 写软元件。
3. **远程操作**：RUN / STOP / 复位 / 时钟设置。
4. **PLC 诊断**：模块信息、错误历史、扫描时间。
5. **机型覆盖实测**：FX5U 之外（FX5S 已能建、iQ-R R00 已能建、LCPU/QCPU 未验）。

> 提醒：真机相关能力同样要"动作 + 读回"——判据取 PLC 侧读数（监视值/错误代码），
> 不能只看对话框返回成功。

## 3. 已经判定堵死的（不要再试，除非有新证据）

| 方向 | 结论 | 证据 |
|---|---|---|
| IEC XML 的 LD / FBD / IL / **SFC** 正文 | 全部被**静默丢弃**（`Program` 建了、0 错、正文空）→ XML 只认 ST | 探针 57–65、123 |
| 局部结构体变量的**成员名访问** | 七条走法全报 `程序(...)转换中` 2 错；要按成员名访问就把变量提到**全局** | 探针 66/75/76/77/144 |
| 导航树双击打开程序（稳定版） | 能打开，但**冷/热交替失败**（同一像素一次成一次不成）；已撤出能力表，`uia.open_program` 只作尽力而为 | 探针 124b–131、12 次冷热运行 |
| 梯形图用 F5/F7 快捷键画 | 对格位挑剔，同一像素一次成功一次报「执行位置不正确。」；必须用工具栏按钮的 UIA Invoke | PITFALLS 五十一 |

## 4. 关键技术底账（免得重新摸）

- **工程文件**：`.gx3` 是 ZIP。`!!Config.xml`（`Unit`）、`ConvertData/Progress.txt`（阶段/错误数）、
  每程序一套 `*_STDB.db`（ST 明文）/ `*_LDDB.db`（LAD DSL）/ `*_SFCDB.db` / `*_FBDDB.db`，
  外加 `*_StepInfo.db`（`T_Step`/`T_SourcePos`）、`*_MilDB.db`（IL 流）、`*_DC.db`（软元件表）、
  `LabelData.db`（标签）、以及 `.h/e/` 下的内嵌 git 仓库。
- **LAD DSL 规格**：`docs/LADDER_DSL.md`（元素/坐标/多梯级的完整说明）。
- **坑清单**：`docs/PITFALLS.md`（54 条，五十一~五十四 是梯形图）。
- **已证伪能力**：`docs/UNSUPPORTED.md`。
- **读数白名单**：`docs/VERIFY.md` 记着每轮的逐条耗时与判据读数。
- **真实样例**：外部导入的产线工程 `*.gx3`（4 个，
  含真实梯形图，可当 DSL 对照）。

## 5. 协作约定（用户明确说过）

- 干活时**不要主动因上下文收口**；上下文余量另有机制。
- 每批改动都要：单跑 → 三轮全量（2 同序 + 1 乱序）→ 结果写进 `docs/VERIFY.md` → 推两个仓库。
- 没打通的不许进能力表，写进 `UNSUPPORTED.md`（`AGENTS.md` 第 1 条）。
- 推代码前有 `pre-push` 钩子把关（远端 SSH / 五处数字一致 / selftest / 离线测试）；
  换机器先跑 `python tools/install_hooks.py`。
- 远端默认分支是 **`main`**（曾经默认 `master` 停在 0.1，导致“推了 main 但页面是旧版”，已修）；
  推之前确认 `git ls-remote --heads origin` 只有 `main`。
- GUI 会抢前台；用户接受这一点（他选择"按现状继续"）。
