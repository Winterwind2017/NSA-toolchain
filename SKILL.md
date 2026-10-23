---
name: ww-gxworks-automation
description: >
  用 gxkit 在本机 MELSOFT GX Works3（三菱 PLC 编程）上做离线工程自动化，
  并**用工程文件读数验证结果**。当用户要求新建 FX5U 工程、把 ST 代码写进程序并读回校验、
  做全部转换（编译）、查编译错误在哪个阶段/哪一行、跑程序检查（指令/双线圈/软元件）、
  批量生成多个 .gx3、导入全局标签 XML、解包看步与源码对应关系/编译 IL/软元件表、
  另存或重开工程，或问"GX Works3 能不能自动化 / 某个菜单为什么没反应"时使用。
  内含实测通过的配方、必须检查的判据、已证伪不可用的路径，以及 GX Works3 特有的坑
  （没有 COM、必须前台激活、未转换不给存盘、XML 标签放错位置会被静默忽略）。
  Use for MELSOFT GX Works3 offline automation: new FX5U project, ST program entry and
  read-back, compile-all and per-stage/per-line error attribution, program check,
  batch .gx3 generation, global-label XML import, offline .gx3 unpacking
  (source / steps / IL / devices / labels), save and reopen.
---

# GX Works3 自动化（gxkit）

引擎 **GX Works3 1.117.0.1**（`D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe`）。
目标机型 **FX5U**，程序语言 **ST**，范围 **仅离线**（不写 PLC）。

## 0. 先记住四件事

1. **没有 COM、没有 API、没有命令行开关**。只有 `GXW3.exe <project.gx3>` 这一种启动方式。
2. **一切操作都是真实鼠标键盘**：窗口必须真的在前台（`GetForegroundWindow()==hwnd`）。
3. **判据只认读回来的东西**：`.gx3` 里的 `StBlocks.data`（源码明文）、
   `ConvertData/Progress.txt`（编译日志）、`LabelData.db`，以及 `程序检查` 的 UIA 文本。
4. **每一步都要验证**：粘贴后看标题 `N步`，保存后看 mtime 变化，导入后看标签数——这些都会偶发失败。

## 1. 跑起来

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest            # 离线自检（25 条）
python -m gxkit caps                # 列能力
python -m gxkit apply --xml build.xml --dry   # 离线预检一份 XML（不开 GX Works3）
python -m gxkit apply --xml build.xml         # 一条命令：导入→编译→存盘→报告（约 2.5 分钟）
python -m gxkit run --workdir D:\tmp\run1     # 真机全量，约 53 分钟
python -m gxkit meta D:\tmp\run1\project_save.gx3   # 读 Config + 编译日志
```

日常干活就用 `apply`：它打印并写出 apply_report.json（程序/功能块/结构体/标签、
导入是否生效、源码块数、步数、编译错误、失败阶段），退出码 0 才算可交付。

## 2. 已打通的能力（详见 capabilities.md）

| 场景 | 能力 | 关键点 |
|---|---|---|
| 新建工程 | `project.new` | Ctrl+N → 系列=FX5CPU(3)、机型=FX5U(0)、语言=ST(1) |
| **换机型** | `project.new_rcpu` / `project.new_fx5s` | 只改 series/model：RCPU=1（28 机型）、FX5CPU=3（FX5U/FX5UJ/FX5S）；读回 `Unit` 验证 |
| **机型无关性** | `program.rcpu_roundtrip` | iQ-R(R00) 上粘贴→转换→读回源码全对（4 步 0 错） |
| 存盘 | `project.save` | 文件名 Edit cid=1148（**按类名取**）、保存按钮 cid=1（同） |
| 看工程 | `project.meta` | `!!Config.xml` → `Unit="FX5U"`；ZIP 条目数 |
| 写程序 | `program.paste_st` | 点进编辑区 → Ctrl+A → 粘贴 → 转换（标题出现 `N步` 才算落地） |
| **读源码** | `program.read_st` | `*_STDB.db` 的 `StBlocks.data` 是**明文**，逐字比对 |
| **步↔源码** | `inspect.source_map` | `T_SourcePos` 的 `Row=/Col=/StrLen=` + 片段 |
| **编译 IL** | `inspect.mil` | `*_MilDB.db` 的 `MIL.data`（`op=` 流） |
| **软元件表** | `inspect.devices` | `*_DC.db` `DEVICE_DATA`（FX5U 2935 行 + 注释） |
| 编译 | `build.convert_all` | Shift+Alt+F4，保存后读 `Progress.txt` |
| 程序检查 | `build.program_check` | 工具 → 程序检查 → 执行 → `程序检查已完成。无错误。` |
| 错误定位（阶段） | `build.error_detail` | `Progress.txt` 的 `failed_stages` |
| **错误定位（行）** | `build.locate_error_line` | 前缀二分：`k` 通过、`k+1` 失败 → 第 `k+1` 行 |
| **标签导入** | `label.import_xml` | `Instances/Configuration/GlobalVars` + 唯一行号 |
| **多类型标签** | `label.multi_type` | BOOL/WORD/DWORD：初值必须与类型匹配（BOOL→FALSE、WORD→0） |
| **程序新建（XML）** | `program.import_xml` | `Program` + `Resource/ProgramInstance`，且删掉 `<Vars>` |
| **程序+功能块（XML）** | `program.import_fb` | `Program` 必须在 `FunctionBlock` 之前；FB 删 `<Parameters>` |
| **功能块实例（XML）** | `program.import_fb_instance` | 程序里 `InstFB : FBInst` + 正文 `InstFB();` |
| **结构体（XML）** | `datatype.import` | `DataTypeDecl` 成员**保持样例原样**；判据用 UIA 导航树 |
| **结构体变量** | `datatype.member_var` | 必须带 `VariableStructDeviceAssignment`（成员绑 B0/W0/B10…），且与结构体同文档 |
| **自定义成员** | `datatype.custom_members` | `Member` 全在前、`<AddData>` 留在最后；成员名随便起 |
| **成员名访问** | `datatype.member_access` | 结构体标签必须放**全局**（`GlobalVars`），正文才能写 `GS1.MyBool` |
| 批量 | `batch.projects` | 同会话连续粘贴变体 + `工程 → 另存为` |
| L4 | `project.reopen` | 存盘 → 关工程 → 重开 → `N步` 仍在 |

## 3. 判据（不看返回值）

| 判据 | 来源 | 期望 |
|---|---|---|
| 机型 | `!!Config.xml` | `Unit="FX5U"` |
| 是否 ST | 窗口标题 | 含 `[PRG] [ST]` |
| 步数 | 窗口标题 | `N步`，N≥2 |
| 编译结果 | `ConvertData/Progress.txt` | `错误：0、警告：0` |
| 失败阶段 | 同上 `failed_stages` | 至少一个阶段 errors>0 |
| 程序检查 | 对话框 UIA | `程序检查已完成。无错误。` |
| 源码读回 | `*_STDB.db` 的 `StBlocks.data` | 与贴进去的**逐字相同**（比较时去空白） |
| 程序清单 | `Progress.txt` 的 `程序(xxx)` | 出现新程序名，数量 +1 |
| 标签导入 | `LabelData` | 出现 `LBL_A/B/C`（54→75 行） |
| 局部标签 / FB 变量 | `LabelData` 的 `ColumnID=2` | 出现 `LocBool`/`FB_Bool` 等 |
| 功能块建出来 | 多一份 `*_STDB.db` + FB 变量名 | 正文与变量都在（FB 不进 `程序(...)` 清单） |
| 结构体建出来 | **UIA 导航树**（uia.py 的 find_names） | 出现 `StructGen …`（`.gx3` 里没有明文） |

## 4. 别踩这些坑（每条都真实踩过）

1. **窗口不在前台 → 什么都没反应**。修：`ShowWindow(SW_RESTORE)` + `SwitchToThisWindow` +
   `SetForegroundWindow`，仍不行就**点一下标题栏**，再校验 `GetForegroundWindow()`。
2. **壳对话框 cid 撞车**：`cid=1148` 命中 ComboBoxEx32/ComboBox/Edit，`cid=1` 命中 `FolderView`。
   必须 `cls="Edit"` / `cls="Button"` 过滤。
3. **未转换不能保存**：必须 `粘贴 → 全部转换 → 保存`。
4. **UIA 子菜单项不能直接 Invoke**：先 `Alt+字母` 弹出菜单（出现 `XTPPopupBar`）再点。
5. **一条能力一个干净会话**；共用一个进程时"关工程→新建→保存"会状态漂移。
6. **批量要改代码、不要新建工程**：同一工程里连续粘贴 + `工程 → 另存为`。
7. **`工程校验` 不是校验本工程**，它是两工程比对。
8. **`程序检查` 要求已转换**，否则弹"程序中存在未转换的梯形图…"。
9. **XML 的 `GlobalVars` 必须在 `Instances/Configuration` 下**，放错会被**静默忽略**。
10. **克隆样例变量后必须改唯一 `VariableLineNumber`**，否则只导入第一条。
11. **保存偶发不落地**：`Ctrl+S` 之后要等 **mtime 变化**，并用读回源码确认。
12. **`save_as` 遇到文件被占用会改名**：后续读取要用它返回的 `path`，不能用你传进去的名字。
13. **行级错误是"二分推断"**：编译器不给行号，`转换结果` 面板是自绘视图读不到。
14. **每个程序一套 SQLite**（STDB/StepInfo/MilDB）：只读第一个会漏掉别的程序，
    表现为"导入成功却读不到源码"。
15. **XML 建程序要两处同时存在**：`Types/GlobalNamespace/Program` +
    `Instances/Configuration/Resource/ProgramInstance`（同名）；
    还要**删掉 `<Vars>`**，否则引用 FBPou1/Struct1/TIMER 等不存在的类型。
16. **导入是非幂等的**：判据没过不要重导，会建出 `PrgGen_2`；先修判据。
17. **程序体比较要"去空白"**：导入后源码会多一个空行（`\r\n\r\n`）。
18. **Alt 系列用 PostMessage，Ctrl 系列用 SendInput**。反直觉但实测如此：
    `SendInput` 的 `Alt+P` 有时到不了窗口（菜单不弹、新建对话框不出现）；
    而 `PostMessage` 的 `Ctrl+S`/`Ctrl+N` 会被 MFC 加速键表忽略。
19. **窗口会以 135×37 "折叠"启动**：这种状态菜单栏不存在，`Ctrl+N` 也不弹窗。
    要 `SW_RESTORE` + `MoveWindow` 到 1280×900；句柄失效时 `GetWindowRect`
    会抛 `error 1400`，必须当作"重新取主窗"而不是异常。
20. **`Ctrl+S` 新建工程后经常不弹"另存为"**：存盘会变空操作（文件不存在）。
    `save_as` 应**菜单优先**：`工程 → 另存为(A)` → 填 cid=1148 → 点 cid=1。
21. **上一轮进程没退干净会"卡在已有实例"**：窗口在、菜单不响应。
    每条能力之间 `taskkill /IM GXW3.exe /T`。
22. **`Program` 必须排在 `FunctionBlock` 之前**：顺序反了整份导入被**静默忽略**
    （0 错、连程序都不建、`Progress.txt` 只剩 `ProgPou`）。
23. **功能块要删 `<Parameters>`**（它引用样例变量 `fb1_*`），`Vars` 只留一块；
    FB 的样例变量没有 `VariableLineNumber`，补唯一行号更稳。
24. **功能块不会出现在 `程序(...)` 清单里**：判定它建出来靠"多一份 STDB（正文）"
    + "`LabelData` 里有它的变量名"。
25. **自定义结构体成员没问题，卡的是元素顺序**：`UserDefinedTypeSpec` 里
    `Member` 全部在前、`<AddData>` 必须留**最后**。顺序反了（例如先删成员再
    append，把样例的 AddData 挤到最前面）整份导入被**静默丢弃**——0 错、连程序
    都不建、导航树里也没有结构体。把 `<AddData>` 挪回最后立刻成功。
26. **结构体类型的变量必须带成员级软元件分配**：`<AddData>` 里要有
    `VariableStructDeviceAssignment`（成员逐个绑 B0/W0/B10…，嵌套成员再套 `<Struct>`）。
    没有它 `局部标签定义检查` 报 1 个错；同一段 XML 加上它就是 0 错。
27. **结构体与程序必须同文档导入**：先导结构体、再导程序，后导的那份仍报转换错。
    嵌套成员类型（Struct2）也要一起导，成员名才会全出现在 `LabelData`。
28. **按成员名访问要用全局结构体标签**：同一个结构体，放程序 `<Vars>`（局部）里写
    `S1.MyBool` 会转换报错；放 `Instances/Configuration/GlobalVars`（全局，带成员级
    软元件分配、**不要 Address**）就能写 `GS1.MyBool := NOT GS1.MyBool;`（0 错）。
    导入后 `Progress.txt` 会多出 `结构体(<类型名>)的定义检查中`，可当判据。
    局部结构体标签按成员名访问试过五条路（private/public、`:= TRUE`、整体 `<Address>`、
    结构体前置）**全不通**：三条转换报错、两条整份丢弃。
29. **非 BOOL 标签的初值必须与类型匹配**：克隆 BOOL 模板做 WORD/DWORD 时，
    `<SimpleValue value="FALSE">` 会让**一个标签都不落地**（连 `Global1` 阶段都不出现）。
    BOOL→FALSE、WORD/DWORD/INT→0。
30. **不要给 `<Variable>` 加自定义属性**：我加过 `template="variable"` 当标记，
    整份标签导入被静默忽略。元信息放代码里，别写进 XML。
31. **导入"静默什么都没进"时可以重试**；一旦目标程序出现就**绝不能重试**（非幂等）。
32. **XML 骨架别每次去读 MELSOFT 的样例**：升级换样例会让生成器整批静默失效。
    现在首次复制到 `%LOCALAPPDATA%/gxkit/skeleton.xml` 并记 sha256，指纹变了自动重建；
    `GXKIT_TEMPLATE=<文件>` 可绕开安装目录。
33. **手写骨架能导入程序/标签/全局结构体，但局部标签不落地**（`locals_found=0` + 转换 2 错）。
    已排除 title/AddData 顺序/Remark/InitialValue/BodyProperties 五个因素，
    要自给自足得继续做逐元素 diff 二分（记在 gxkit 的 `docs/EXPAND_BACKLOG.md`）。

## 5. 明确不做

- 在线（写入 PLC / 监视）：需要真实 PLC 或模拟器，用户口径只做离线。
- 梯形图内容：编辑器自绘，UIA 没有单元格；ST 已覆盖需求。
- 编译器原话（错误消息文本）：没有可读口。
- WORD/DINT 标签导入：只验证了 BOOL。

## 6. 新增能力的姿势

```powershell
python tools/add_cap.py spec.json    # cap id 唯一性检查 + 自检
```

能力必须"动作 + 从软件读回"；读不到就当失败。
