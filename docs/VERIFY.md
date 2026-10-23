# 全量验证记录

> 目的：在一台装了 GX Works3 的机器上，按下面几步就能复现"25 条能力全过"。

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
# 自检通过：25 条能力，动作与判据齐全

# 2) 离线测试（含 inspect / xmlgen 的合成 .gx3）
python -m pytest -q tests
# 23 passed

# 3) 真机全量（约 53 分钟；每条能力一个干净会话）
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
| 2026-10-23 | **16/16（v0.4，同一份代码第二次）** | 1911.4 s |
| 2026-10-23 | **17/17（v0.5，新增 program.import_fb）** | 2045.0 s |
| 2026-10-23 | **17/17（v0.5，同一份代码第二次）** | 2047.8 s |
| 2026-10-23 | **19/19（v0.6，新增功能块实例 + 结构体）** | 2344.3 s |
| 2026-10-23 | **19/19（v0.6，同一份代码第二次）** | 2342.9 s |
| 2026-10-23 | **20/20（v0.7，新增 datatype.member_var）** | 2485.6 s |
| 2026-10-23 | **20/20（v0.7，同一份代码第二次）** | 2482.7 s |
| 2026-10-23 | **21/21（v0.8，新增 datatype.custom_members）** | 2630.5 s |
| 2026-10-23 | **21/21（v0.8，同一份代码第二次）** | 2632.2 s |
| 2026-10-23 | **22/22（v0.9，新增 datatype.member_access）** | 2786.3 s |
| 2026-10-23 | **22/22（v0.9，同一份代码第二次）** | 2795.7 s |
| 2026-10-23 | **23/23（v0.10，新增 label.multi_type）** | 3027.9 s |
| 2026-10-23 | **23/23（v0.10，同一份代码第二次）** | 3060.8 s |
| 2026-10-23 | **25/25（v0.11，含 inspect.programs / project.diff）** | 3272.6 s |
| 2026-10-23 | **25/25（v0.11，同一份代码第二次）** | 3270.9 s |

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

## v0.5 新增一条：program.import_fb（程序 + 功能块 + 局部标签）

| 读数 | 值 |
|---|---|
| program_count / 
ames | 2 / ["ProgPou","PrgFB"] |
| ody_found / b_body_found | true / true |
| locals_found / b_vars_found | 2 / 2（LocBool、LocWord、FB_Bool、FB_Word） |
| labels_before → after | 54 → 76 |
| 
ew_sources | 2（多出程序与功能块各一套 STDB） |
| rrors | 0 |

三条关键规则（都是**静默失败**换来的）：
1. Program 必须排在 FunctionBlock **之前**，否则整份导入被忽略；
2. 功能块要**删掉 <Parameters>**，Vars 只留一块；
3. 功能块不会出现在 Progress.txt 的 程序(...) 清单里——判定它建出来靠
   “多一份 STDB（正文）”+“LabelData 里有它的变量名”。

## v0.6 新增两条

| 能力 | 读数 |
|---|---|
| program.import_fb_instance | programs=[FBInst, ProgPou, PrgFB]、ody_found、b_body_found、instance_type_seen（类型列出现 FBInst）、
ew_sources=2、0 错 |
| datatype.import | program_created（PrgStruct）、struct_node_seen（导航树 StructGen タイトル Struct1）、labels 54→70、0 错 |

这一轮最值钱的教训：
1. **结构体的 <Member> 不能重建**——自己拼成员会让整份导入被静默丢弃；
2. **结构体类型的变量**能落库但 局部标签定义检查 报错，所以结构体的判据改用
   **UIA 导航树**（.gx3 里根本没有结构体明文）；
3. 导入"静默什么都没进"时可以重试，**一旦目标程序出现就绝不能重试**（非幂等）。

## v0.7 新增一条：datatype.member_var（结构体类型的变量）

| 读数 | 值 |
|---|---|
| program_created / programs | true / ["ProgPou","PrgSV"] |
| rrors / ailed_stages | 0 / [] |
| define_stage_seen / define_stage_errors | true / 0（局部标签(PrgSV)定义检查中） |
| struct_node_seen | true（导航树 StructGen …） |
| member_rows_seen | 7（member1_1..4 + member2_1..3） |
| labels_before → after | 54 → 79 |

三条关键规则：
1. 结构体与程序必须在**同一份文档**里导入（先导结构体、再导程序，程序仍报转换错）；
2. 结构体变量必须带 VariableStructDeviceAssignment（成员级软元件分配），
   否则 局部标签定义检查 报 1 个错——同一段 XML 加上它就是 0 错；
3. 嵌套成员类型（Struct2）也要一起导入，7 个成员名才会全部出现在 LabelData。

## v0.8 新增一条：datatype.custom_members（自定义结构体成员）

| 读数 | 值 |
|---|---|
| program_created | true（PrgCust） |
| rrors / ailed_stages | 0 / [] |
| member_rows_seen | 2（MyBool、MyWord，自定义名字） |
| struct_node_seen | true（导航树 StructCust …） |
| labels_before → after | 54 → 64 |

**推翻旧结论**：结构体成员不是"必须保持样例原样"，真正的规则是**元素顺序**——
UserDefinedTypeSpec 里 Member 全部在前，<AddData> 必须在最后。
之前重建成员时把 <AddData> 挤到了最前面，于是整份导入被静默丢弃（探针 73 四个候选全灭）。
只把 <AddData> 挪回最后，同一份自定义成员的 XML 立刻 0 错导入成功（探针 74）。

## v0.9 新增一条：datatype.member_access（正文按成员名访问结构体）

| 读数 | 值 |
|---|---|
| program_created | true（PrgGA） |
| rrors / ailed_stages | 0 / [] |
| struct_define_stage_seen / _errors | true / 0（新阶段 结构体(StructCust)的定义检查中） |
| member_access_in_source | true（源码里 GS1.MyBool := NOT GS1.MyBool;） |
| global_label_seen / struct_type_in_labels | true / true |
| labels_before → after | 54 → 74 |

关键：**结构体标签要放全局**。同一个结构体，放程序 <Vars> 里按成员名访问会转换报错；
放 Instances/Configuration/GlobalVars 里就 0 错（探针 66 vs 75）。

## v0.10 新增一条：label.multi_type（BOOL / WORD / DWORD 全局标签）

| 读数 | 值 |
|---|---|
| labels_landed / labels_wanted | 3 / 3 |
| labels_before → after | 54 → 75 |
| program_created | true（PrgType，正文 LBL_WORD := LBL_WORD + 1;） |
| word_used_in_source | true |
| rrors / ailed_stages | 0 / [] |

两条教训：
1. **初值必须与类型匹配**——WORD 标签若沿用了 BOOL 模板的 <SimpleValue value="FALSE">，
   一个标签都不落地（连 全局标签(Global1)定义检查中 阶段都不出现）。
2. **不要给 <Variable> 加自定义属性**（我曾加 	emplate="variable" 当标记，整份导入被忽略）。

## v0.10 的另一半：datatype.local_member_access 判定为不可行

五条路都试过（private/public、:= TRUE、整体 <Address>、结构体移到程序前面）：
前三种转换报错、后两种整份导入被丢弃。**全局**结构体标签可以按成员名访问
（datatype.member_access，已验证 0 错）。这条结论写进了 UNSUPPORTED.md 与 PITFALLS 三十六。

## v0.11 新增两条（纯离线读数，不碰界面）

| 能力 | 读数 |
|---|---|
| inspect.programs | program_count=1、source_count=1、matched_blocks=1、	otal_steps=4、ody_found=true |
| project.diff | identical_self=true、locks_changed=1、changed_added=1、diff 行 +W0 := W0 + 1; |

project_diff 的比较口径是**去空白后的行序列**（导入会改写换行/空行），
自比必须 identical=True——这是防"diff 永远报有差异"的自检。

## v0.11 新增两条（纯离线读数，不碰界面）

| 能力 | 读数 |
|---|---|
| inspect.programs | program_count=1、source_count=1、matched_blocks=1、	otal_steps=4、ody_found=true |
| project.diff | identical_self=true、locks_changed=1、changed_added=1、diff 行 +W0 := W0 + 1; |

project_diff 的比较口径是**去空白后的行序列**（导入会改写换行/空行），
自比必须 identical=True——这是防"diff 永远报有差异"的自检。

## v0.11 收尾四件事

| 项 | 结果 |
|---|---|
| 模板依赖 | 首次复制到 `%LOCALAPPDATA%/gxkit/skeleton.xml` 并记 sha256，指纹变化自动重建；`GXKIT_TEMPLATE` 可绕开安装目录 |
| 手写骨架 | `templates/base.xml` 能导入程序/标签/全局结构体；**局部标签不落地**（已排除 5 个因素），记入 UNSUPPORTED |
| 一条命令 | `gxkit apply --xml x.xml [--dry]`：预检 → 导入 → 编译 → 存盘 → 报告（实测 142.7 s 通过） |
| 待办 | `docs/EXPAND_BACKLOG.md`：往外扩按预估用时降序排好（LAD 8–16h → iQ-R 4–8h → …） |
