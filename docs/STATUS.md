# gxkit 现状

引擎 **GX Works3 1.117.0.1**，内核 **gxkit 0.15.0**。目标机型 **FX5U**，程序语言 **ST**，范围 **离线**。

## 数字

- 真机通过能力：**37** 条（其中 23 条已全量连跑两次通过；inspect.programs / project.diff 单项通过，**全量复跑待补**）
- 一条能力一个干净会话（启动约 10 s）；`batch.projects` 与 `build.locate_error_line` 是例外（前者同会话连做，后者同会话多次转换）
- 未打通：见 `UNSUPPORTED.md`

## 能力

### 工程与存盘

| id | 做什么 | 判据来源 |
|---|---|---|
| `build.error_messages` | **编译器原话**（读「输出」面板的表格） | 表格 6 列 + 一行 `使用了未定义的标签。`／`0x110E1A20` |
| `project.check` | **工程校验**（与另一个 .gx3 比对） | 结果页 `校验结果` + 状态行 `存在2个不同内容` |
| `project.new_language` | **换程序语言建工程**（ST / SFC / FBD） | 标题分别含 `[ST]` / `[SFC]` / `[FBD/LD]`，Unit 都是 FX5U |
| `batch.new_projects` | 同会话连新建 3 个工程（关闭后重建） | 3 个都存在、源码逐字匹配、0 错 |
| `xmlgen.manual_template` | **手写骨架也能导入**（不再依赖 MELSOFT 样例） | `uses_manual=true`、局部标签 2 个都落地、0 错 |
| `inspect.devices_rcpu` | **iQ-R 软元件模板** | 3345 行、三种设备类型码（含 35），与 FX5U 的 2935 行不同 |
| `program.multi_programs` | **一个工程两个程序** | PrgOne/PrgTwo 都建、两段源码都在、0 错 |
| `datatype.struct_array` | **结构体数组成员 + 元素访问** | `结构体(StructArr)的定义检查中` 0 错、源码含 `Arr[` |
| `program.import_fb_params` | **功能块带参数（IN/OUT/OUT_RETAIN）+ 调用传参** | 程序与 FB 都建成、调用语句在源码、0 错 |
| `project.new` | 新建 FX5U+ST 工程 | 标题含 `[PRG] [ST]` |
| `project.save` | 另存为 `.gx3`（含读回） | 文件存在 + `!!Config.xml` 的 `Unit` |
| `project.new_rcpu` | **新建 iQ-R（RCPU/R00）+ ST 工程** | `!!Config.xml` 读到 `Unit=R00`、`UnitId=4609` |
| `project.new_fx5s` | **新建 FX5S + ST 工程** | `Unit=FX5S` |
| `project.meta` | 解包读 Config/条目数 | ZIP 条目 + Config |
| `project.reopen` | 存盘→关→重开→步数仍在（L4） | 标题文件名 + `N步` |

### 程序

| id | 做什么 | 判据来源 |
|---|---|---|
| `program.paste_st` | ST 代码粘进编辑器 | 标题 `N步` |
| `program.rcpu_roundtrip` | **iQ-R 上粘贴 ST 并读回** | 源码逐字匹配、4 步、0 错 |
| `program.read_st` | **从 `.gx3` 读回 ST 源码** | `StBlocks.data` 与贴进去的逐字相同 |
| `program.import_xml` | **用 XML 新建程序（PrgGen）** | 编译日志出现 `程序(PrgGen)` + 正文进 STDB + 0 错 |
| `program.import_fb` | **用 XML 建程序 + 功能块（带局部标签）** | `PrgFB` 进程序清单、两段正文进 STDB、4 个局部标签进 `LabelData`、0 错 |
| `program.import_fb_instance` | **建功能块并在程序里声明实例、调用** | `程序(FBInst)`+`程序(PrgFB)`、正文含 `InstFB();`、类型列出现 `FBInst`、0 错 |

### 结构体

| id | 做什么 | 判据来源 |
|---|---|---|
| `datatype.import` | **用 XML 建结构体** | UIA 导航树出现 `StructGen …`、程序照常导入、0 错 |
| `datatype.member_var` | **结构体类型的变量（成员级软元件分配）** | `局部标签定义检查` 0 错、导航树有结构体、`LabelData` 里 7 个成员名、整体 0 错 |
| `datatype.custom_members` | **自定义结构体成员（MyBool/MyWord）** | `LabelData` 里出现自定义成员名、导航树有结构体、整体 0 错 |
| `datatype.member_access` | **正文按成员名访问（`GS1.MyBool := ...`）** | 多出 `结构体(StructCust)的定义检查中` 阶段且 0 错、源码含该语句、`GS1` 进 `LabelData`、整体 0 错 |

### 编译与检查

| id | 做什么 | 判据来源 |
|---|---|---|
| `build.convert_all` | 全部转换 | `Progress.txt` 的 `错误：0、警告：0` |
| `build.program_check` | 程序检查（指令/双线圈/软元件） | UIA 文本 `程序检查已完成。无错误。` |
| `build.error_detail` | 定位错在哪个编译阶段 | `Progress.txt` 的 `failed_stages` |
| `build.locate_error_line` | **二分法定位坏行** | 前缀 `k` 通过、`k+1` 失败 → 第 `k+1` 行 |
| `batch.projects` | 同会话连出 3 个工程 | 3 个文件都在 + 各自 0 错 + 大小各不相同 |

### 离线读数（纯 ZIP/SQLite，不碰界面）

| id | 做什么 | 判据来源 |
|---|---|---|
| `inspect.source_map` | 每个 MIL 步 → 源码坐标 | `T_SourcePos` 的 `Row/Col/StrLen` |
| `inspect.mil` | 编译后的 IL 文本 | `MilDB.MIL.data` 的 `op=` 个数 |
| `inspect.devices` | FX5U 系统软元件模板 | `DEVICE_DATA` 2935 行 + 注释 |
| `inspect.programs` | **列程序清单（步数/源码行数/正文）** | `program_list`：程序数、块数、步数、正文都能对上 |
| `project.diff` | **两个工程的源码级差异** | 自比一致（`identical_self`）、改一行就 `blocks_changed=1 / +1` |

### 标签

| id | 做什么 | 判据来源 |
|---|---|---|
| `label.import_xml` | 导入全局标签 XML | `LabelData` 里出现 `LBL_A/B/C`（54→75 行） |
| `label.multi_type` | **BOOL / WORD / DWORD 三种标签** | 3 个名字全进 `LabelData`（54→75）、随后用 WORD 标签写的程序 0 错 |

## 五层判据

1. **文件层**：`.gx3` 存在、大小、`!!Config.xml` 的机型。
2. **源码层**：`StBlocks.data` 就是 ST 原文；`T_SourcePos` 给步→源码坐标。
3. **编译层**：`Progress.txt` 的逐阶段 `Error/Warning` 与 `failed_stages`。
4. **软件层**：`工具 → 程序检查` 的判定文本（UIA 可读）。

## 一条命令干活

```powershell
python -m gxkit apply --xml build.xml --dry        # 只做离线预检（不开 GX Works3）
python -m gxkit apply --xml build.xml              # 导入 -> 编译 -> 存盘 -> 报告
python -m gxkit run --shuffle --seed 7            # 乱序跑一轮（查顺序依赖/状态泄漏）
```

`apply` 会打印并写出报告文件 apply_report.json：程序/功能块/结构体/标签清单、导入是否生效、
源码块数、步数、编译错误、失败阶段。退出码 0 = 可交付。

## 复现

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest
python -m gxkit run --workdir D:\tmp\run1     # 37/37，约 76 分钟
```
