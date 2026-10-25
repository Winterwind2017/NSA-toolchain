# gxkit

**MELSOFT GX Works3 的自动化内核**（工控 PLC 编程）：无 COM、无 API，靠真实界面操作 + 工程文件读数。

引擎：**GX Works3 1.117.0.1**（`D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe`）
目标机型：**FX5U**（MELSEC iQ-F，另支持 FX5S / iQ-R R00）　程序语言：**ST + 梯形图(LAD)**　范围：**仅离线**

> **下次开工先读 [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md)** —— 收口交接单：还没做的方向（SFC/FBD 正文、注释写入……）、
> 已判定堵死的清单、以及"需要真机才能做"的在线能力。

## 为什么长这样

| 尝试 | 结论 |
|---|---|
| COM / ActiveX | ❌ 注册表里没有任何 MELSOFT ProgID，MX Component 也没装 |
| 进程内调托管层 | ❌ `Melco.GXW3.*` 是"契约 + Impl + Proxy"的服务总线，脱离宿主跑不起来 |
| 命令行参数 | ❌ 只有 `GXW3.exe <project.gx3>` 这一种（文件关联就这么写的） |
| **Win32 + UIA 驱动界面** | ✅ 唯一可行：菜单可枚举、对话框可点、编辑器可粘贴 |
| **工程文件读数** | ✅ `.gx3` 是 ZIP，内含 SQLite 与纯文本编译日志 |

所以内核的分层是：

```
动作层（真实鼠标/键盘）  →  读数层（解包 .gx3 / 读 Progress.txt）  →  判据层
```

## 安装 / 使用

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest                       # 离线自检（不需要 GX Works3）
python -m gxkit caps                           # 列能力
python -m gxkit run --workdir D:\tmp\run1      # 真机跑全部 42 条（约 105 分钟）
python -m gxkit run --only project.save        # 只跑一条
python -m gxkit meta D:\tmp\run1\project_save.gx3   # 读工程元信息与编译日志
```

## 判据从哪来（不看返回值）

| 判据 | 来源 |
|---|---|
| 工程存在 / 大小 | `.gx3` 文件系统 |
| 机型 | `.gx3` 里的 `!!Config.xml`（`Unit="FX5U"`） |
| 是否 ST | 窗口标题里的 `[ProgPou [PRG] [ST] N步]` |
| 步数 | 标题里的 `N步` |
| **编译结果** | `.gx3` 里 `ConvertData/Progress.txt`（纯文本：`错误：0、警告：0`） |
| 错在哪个阶段 | 同上，逐阶段的 `Error/Warning`（`failed_stages`） |
| **程序检查判定** | `工具 → 程序检查` 执行后对话框的 UIA 文本：`程序检查已完成。无错误。` |
| **ST 源码** | **每个程序一套** `*_STDB.db`，`StBlocks.data` 就是原文（可逐字比对） |
| 程序清单 | `Progress.txt` 里的 `程序(xxx)` 阶段名（软件自己列的） |
| 步→源码坐标 | `*_StepInfo.db` 的 `T_SourcePos`（`Row=,Col=,StrLen=`） |
| 编译 IL | `*_MilDB.db` 的 `MIL.data`（`op=` 指令流） |
| 软元件模板 | `*_DC.db` 的 `DEVICE_DATA`（FX5U 2935 行 + 注释） |
| 标签 | `LabelData.db`（`LabelTbl`/`RowTbl`/`ColumnDataTbl`；名字在 `ColumnID=2`） |
| 功能块 | FB 的正文同样落在一份 `*_STDB.db` 里（没有独立的 FB 清单，靠正文与局部标签判定） |

`Progress.txt` 是这套内核最有价值的判据：**编译 0 错 0 警是硬事实**，不依赖任何界面抓取。
`程序检查` 是第二层：它在编译通过之后继续查指令用法、双线圈、软元件/标签一致性。
`StBlocks.data` 是意外之喜：程序源码在 `.gx3` 里是**明文**，所以"读回校验"可以做到逐字比对。
而且**一个程序一套 SQLite**（STDB/StepInfo/MilDB 各一份），所以"工程里几个程序"可以直接数出来。

## 行级错误怎么来的（不是编译器原话）

编译失败时 `T_Step` 是空的（没有步就没有源码坐标），编译器也不给行号。所以用**前缀二分**问编译器：

```
lines[0:k] 通过、lines[0:k+1] 失败  →  第 k+1 行就是坏行
```

8 行程序、坏行注入在第 5 行 → 4 次转换就定位到第 5 行（`k=8 失败 / k=4 通过 / k=6 失败 / k=5 失败`）。
这是**推断**，不是编译器原文；原文那条路（`转换结果` 面板）是自绘视图，读不到。

## 批量

`batch.projects` 在**同一个** GX Works3 会话里连续做 N 个工程：
粘贴变体代码 → 全部转换 → `工程 → 另存为` 落到新文件。
3 个变体约 130 s（比每条起一次会话省下 ~1 分钟），判据是"每个文件都在 + 各自 0 错 + 大小各不相同"。

## 目录

```
src/gxkit/win.py       Win32 底层（窗口/点击/按键/剪贴板/前台激活）
src/gxkit/uia.py       UIA 薄封装（菜单项、按钮定位）
src/gxkit/session.py   GX Works3 会话（新建/另存/粘贴/转换/程序检查/XML 导入）
src/gxkit/inspect.py   **离线读 .gx3**（源码/步/IL/软元件/标签）
src/gxkit/xmlgen.py    生成全局标签的 IEC 61131-10 XML（以官方样例为骨架）
src/gxkit/actions.py   每条能力的动作
src/gxkit/caps.py      能力表（唯一事实来源）
src/gxkit/judges.py    判据
src/gxkit/runner.py    一条能力 = 一个干净会话
docs/DEPENDENCY.md     依赖关系与开发顺序
docs/PITFALLS.md       踩过的坑（务必先读）
docs/STATUS.md         当前状态
```

## 已知边界

- 只能离线（不写入 PLC）；在线能力需要真实 PLC 或模拟器，未做
- UI 是日文版；菜单/控件 id 依赖日文界面，换语言需重建映射
- 每条能力 ~10 s 启动 + 操作，全套 **~35 分钟**（17 条）
- 行级错误是"前缀二分推断"，不是编译器原文（面板读不到）
- 梯形图内容不走 XML；程序体用编辑器粘贴，全局标签走 XML 导入（仅验证 BOOL）
