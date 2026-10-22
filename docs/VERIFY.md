# 全量验证记录

> 目的：在一台装了 GX Works3 的机器上，按下面几步就能复现"16 条能力全过"。

## 环境

| 项 | 值 |
|---|---|
| 引擎 | GX Works3 1.117.0.1 @ `D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe` |
| 宿主 Python | `C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe` |
| 依赖 | `pywin32`、`comtypes`、`Pillow`（UIA 走 `comtypes` 生成 `UIAutomationClient`） |
| 目标机型 | FX5U（`FX5CPU` 系列），程序语言 ST |

## 步骤

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'

# 1) 离线自检（不需要打开软件）
python -m gxkit selftest
# 自检通过：16 条能力，动作与判据齐全

# 2) 离线测试（含 inspect / xmlgen 的合成 .gx3）
python -m pytest -q tests
# 14 passed

# 3) 真机全量（约 31 分钟；每条能力一个干净会话）
python -m gxkit run --workdir D:\bililive\gxkit\_runs\g1
```

## 单条验证

```powershell
python -m gxkit run --only label.import_xml --workdir D:\tmp\one
python -m gxkit run --only build.locate   --workdir D:\tmp\loc
python -m gxkit meta D:\tmp\one\label_import_xml.gx3
```

## 历史记录

| 日期 | 结果 | 会话时长 |
|---|---|---|
| 2026-10-22 | 6/6（v0.1） | 439.8 s |
| 2026-10-22 | 6/6（v0.1） | 427.1 s |
| 2026-10-22 | 9/9（v0.2） | 793.3 s |
| 2026-10-22 | 8/9（v0.2，error_detail 偶发粘贴未落地） | 824.8 s |
| 2026-10-22 | 9/9（v0.2，error_detail 加固后） | 816.6 s |
| 2026-10-22 | 9/9（v0.2，加固后第二次） | 817.6 s |
| 2026-10-22 | 15/15（v0.3，首版） | 1432.3 s |
| 2026-10-22 | 14/15（v0.3，batch 判据偏弱） | 1436.1 s |
| 2026-10-22 | 10/15（v0.3，粘贴/存盘抖动暴露） | 1427.3 s |
| 2026-10-22 | 13/15（v0.3，加固一半） | 1456.6 s |
| 2026-10-22 | 14/15（v0.3，内容判据后仍有一次存盘未落地） | 1476.6 s |
| 2026-10-22 | **15/15（v0.3，加固完成）** | 1712.1 s |
| 2026-10-22 | **15/15（v0.3，加固完成后第二次）** | 1714.1 s |
| 2026-10-22 | 15/16（v0.4，二分读不到结果被当成通过） | 1876.2 s |
| 2026-10-22 | **16/16（v0.4，新增 program.import_xml）** | 1833.0 s |
| 2026-10-22 | **16/16（v0.4，输入/存盘改为菜单优先 + PostMessage）** | 1929.0 s |

## v0.3 加固了什么（每一轮失败换来的）

| 抖动 | 现象 | 加固 |
|---|---|---|
| 粘贴 | 标题没有 `N步`，转换得到"空程序 1 错" | `_paste_until_steps`：看到步数才算贴成功，最多 3 次 |
| 存盘 | `Ctrl+S` 4 s 就返回，读回来还是 `;` | `save()` 等 **mtime 变化**（3 次 / 12 s）+ `_saved_program` 用读回源码确认 |
| 另存为对话框 | "没有文件名输入框" | `save_as` 整体重试 3 次（先关对话框再重新发起） |
| 标签导入 | `labels_found=0` | 以"读回的标签数"为后置条件，不达标再导一次 |
| 二分定位 | `found_line=7` | 读 `save_as` **实际写成的路径**（占用时会改名） |
| 批量判据 | `distinct_sizes=2` 假阳性 | 改成读回源码逐字匹配（`distinct_sources` / `content_match`） |

## v0.3 新增六条的读数

| 能力 | 会话时长 | 读数 |
|---|---|---|
| `program.read_st` | 80.9 s | 读回源码与贴进去的**逐字相同**（`matches=True`），`steps=4` |
| `inspect.source_map` | 80.9 s | `steps=4`、`rows=2`、`snippets=4`，首片段 `B0 := NOT B0` |
| `inspect.devices` | 50.9 s | `device_rows=2935`、`device_types=2`、`commented=2935` |
| `inspect.mil` | 80.9 s | `mil_rows=1`、`op_count=4`、`mil_chars≈120` |
| `label.import_xml` | 99.5 s | `labels_before=54` → `labels_after=75`、`labels_found=3`、`errors=0` |
| `build.locate_error_line` | 215.3 s | `found_line=5`（注入在 5）、`iterations=4`，历史 `k=8 失败 / k=4 通过 / k=6 失败 / k=5 失败` |

## v0.4 新增一条：program.import_xml（用 XML 建程序）

| 读数 | 值 |
|---|---|
| program_count | 2（ProgPou + PrgGen） |
| ody_found | True（源码进 *_STDB.db，UTF-16LE 存的 TEXT，比较时去空白） |
| steps_added | 5 |
| 
ew_sources | 1（多出一套 STDB） |
| rrors | 0 |

关键三步（缺一不建程序）：
1. Types/GlobalNamespace/Program（名称 = 新程序名）；
2. Instances/Configuration/Resource/ProgramInstance 同名实例；
3. **删掉 <Vars>**（否则引用 FBPou1/Struct1/TIMER 等不存在的类型）。

另：program.read_st 与 inspect.* 改成**遍历全部 *_STDB.db / *_StepInfo.db / *_MilDB.db**，
因为每个程序一套 SQLite；只读第一个会把导入的程序看漏。

## v0.4 的 UI 加固（这一轮踩的坑最多）

| 现象 | 根因 | 修法 |
|---|---|---|
| 新建工程对话框没出现（连跑 5 次） | 窗口以 135×37 折叠启动，菜单栏不存在 | nsure_size() 还原并 MoveWindow 到 1280×900 |
| 整个 run 卡在第一项 30 分钟 | 句柄失效后 GetWindowRect 抛 rror 1400 | nsure_size 返回 invalid，_focus 重新取主窗 |
| Alt+P 时灵时不灵 | SendInput 的 Alt 组合到不了窗口 | 改成 PostMessage(WM_SYSKEYDOWN) 投递 |
| Ctrl+S 反而不生效 | PostMessage 的 Ctrl 被 MFC 加速键忽略 | Ctrl 系列回到 SendInput |
| project.save 文件不存在 | 新建工程后 Ctrl+S 不弹另存为 | save_as 菜单优先：工程 → 另存为(A) |
| 后面的能力连续挂在 
ew_project | 上一轮 GXW3 没退干净，新实例"已有实例" | 每条能力前 	askkill /IM GXW3.exe /T |
