---
name: ww-gxworks-automation
description: >
  用 gxkit 在本机 MELSOFT GX Works3（三菱 PLC 编程）上做离线工程自动化，
  并**用工程文件读数验证结果**。当用户要求新建 FX5U 工程、把 ST 代码写进程序、
  做全部转换（编译）、检查编译错误数、另存/重开工程，或问
  "GX Works3 能不能自动化 / 某个菜单为什么没反应"时使用。
  内含实测通过的配方、必须检查的判据、已证伪不可用的路径，以及 GX Works3 特有的坑
  （没有 COM、必须前台激活、未转换不给存盘）。
  Use for MELSOFT GX Works3 offline automation: new FX5U project, ST program entry,
  compile-all verification, save/reopen, and diagnosing silent no-op GUI actions.
---

# GX Works3 自动化（gxkit）

引擎 **GX Works3 1.117.0.1**（`D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe`）。
目标机型 **FX5U**，程序语言 **ST**，范围 **仅离线**（不写 PLC）。

## 0. 先记住三件事

1. **没有 COM、没有 API、没有命令行开关**。只有 `GXW3.exe <project.gx3>` 这一种启动方式。
2. **一切操作都是真实鼠标键盘**：窗口必须真的在前台（`GetForegroundWindow()==hwnd`），
   否则 Alt 菜单、Ctrl+N 全部"点了没反应"。
3. **判据只认工程文件**：`.gx3` 是 ZIP，里面的 `ConvertData/Progress.txt` 是纯文本编译日志，
   `错误：0、警告：0` 是硬事实。

## 1. 跑起来

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest            # 离线自检
python -m gxkit caps                # 列能力
python -m gxkit run --workdir D:\tmp\run1     # 真机全量，约 7–8 分钟
python -m gxkit meta D:\tmp\run1\project_save.gx3   # 读 Config + 编译日志
```

## 2. 已打通的能力（详见 capabilities.md）

| 场景 | 能力 | 关键点 |
|---|---|---|
| 新建工程 | `project.new` | Ctrl+N → 系列=FX5CPU(3)、机型=FX5U(0)、语言=ST(1) → 确定 → "添加模块"再确定 |
| 存盘 | `project.save` | Ctrl+S → 壳对话框：文件名 Edit 的 cid=1148（**必须按类名取**）、保存按钮 cid=1（同样按类名） |
| 看工程 | `project.meta` | 解包：`!!Config.xml` → `Unit="FX5U"`；ZIP 条目数 |
| 写程序 | `program.paste_st` | 点进编辑区（窗口 45% 位置）→ Ctrl+A → 粘贴 → 转换 |
| 编译 | `build.convert_all` | Shift+Alt+F4，之后读 `Progress.txt` |
| L4 | `project.reopen` | 存盘 → 关工程 → 重开 → 标题里的 `N步` 仍在 |

## 3. 判据（不看返回值）

| 判据 | 来源 | 期望 |
|---|---|---|
| 机型 | `.gx3` 的 `!!Config.xml` | `Unit="FX5U"` |
| 是否 ST 程序 | 窗口标题 | 含 `[PRG] [ST]` |
| 步数 | 窗口标题 | `N步`，N≥2 |
| **编译结果** | `.gx3` 的 `ConvertData/Progress.txt` | `错误：0、警告：0` |
| 工程大小 | 文件系统 | 300 KB – 5 MB |

## 4. 别踩这些坑（每条都真实踩过）

1. **窗口不在前台 → 什么都没反应**。修：`ShowWindow(SW_RESTORE)` + `SwitchToThisWindow` +
   `SetForegroundWindow`，仍不行就**点一下标题栏**，然后校验 `GetForegroundWindow()`。
2. **壳对话框 cid 撞车**：`cid=1148` 命中 ComboBoxEx32/ComboBox/Edit 三个句柄，`cid=1` 会命中
   `FolderView`。必须 `cls="Edit"` / `cls="Button"` 过滤，否则 `WM_SETTEXT` 写进 ComboBox、
   `BM_CLICK` 点在文件夹列表上，表现为"保存了但文件不存在"。
3. **未转换不能保存**：弹"全局标签处于未转换状态…请执行全部转换或转换后再保存工程"。
   顺序必须 `粘贴 → 全部转换 → 保存`。
4. **UIA 子菜单项不能直接 Invoke**（`COMError -2146233083`）：先 `Alt+字母` 弹出菜单
   （出现 `XTPPopupBar` 窗口），再对 popup 里的 MenuItem Invoke。
5. **一条能力一个干净会话**：共用一个进程时，"关工程→新建→保存"会状态漂移，
   出现标题还带旧路径、保存被静默成另存、对话框不弹。启动多花 10 s，换确定性。
6. **`.gx3` 里的程序源码读不出来**：`_Project.txc` 二进制、程序体在 `.w3pa`；
   SQLite `StBlocks.data` 只有 1 字符。所以程序内容走编辑器粘贴，不要指望读回源码。

## 5. 明确不做

- 在线（写入 PLC / 监视）：需要真实 PLC 或模拟器，用户口径只做离线。
- 梯形图内容：编辑器自绘，UIA 没有单元格，无法程序化写网络；ST 已覆盖需求。
- IEC 61131-10 XML 建程序：通道存在，但只稳定导入全局标签，`<Program>` 不建新程序。

## 6. 新增能力的姿势

```powershell
python tools/add_cap.py spec.json    # 会做 cap id 唯一性检查 + 自检
```

能力必须"动作 + 从软件读回"；读不到就当失败。
