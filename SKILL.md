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
python -m gxkit selftest            # 离线自检（15 条）
python -m gxkit caps                # 列能力
python -m gxkit run --workdir D:\tmp\run1     # 真机全量，约 28 分钟
python -m gxkit meta D:\tmp\run1\project_save.gx3   # 读 Config + 编译日志
```

## 2. 已打通的能力（详见 capabilities.md）

| 场景 | 能力 | 关键点 |
|---|---|---|
| 新建工程 | `project.new` | Ctrl+N → 系列=FX5CPU(3)、机型=FX5U(0)、语言=ST(1) |
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
| 源码读回 | `StBlocks.data` | 与贴进去的**逐字相同** |
| 标签导入 | `LabelData` | 出现 `LBL_A/B/C`（54→75 行） |

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
