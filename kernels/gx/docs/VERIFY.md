# 全量验证记录

> 目的：在一台装了 GX Works3 的机器上，按下面几步就能复现"42 条能力全过"。

## 环境

| 项 | 值 |
|---|---|
| 引擎 | GX Works3 1.117.0.1 @ `D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe` |
| 宿主 Python | `python` |
| 依赖 | `pywin32`、`comtypes`、`Pillow`（UIA 走 `comtypes` 生成 `UIAutomationClient`） |
| 目标机型 | FX5U（`FX5CPU` 系列），程序语言 ST |

## 步骤

```powershell
$env:PYTHONPATH='<repo>\gxkit\src'

# 1) 离线自检（不需要打开软件）
python -m gxkit selftest
# 自检通过：42 条能力，动作与判据齐全

# 2) 离线测试（含 inspect / xmlgen 的合成 .gx3）
python -m pytest -q tests
# 23 passed

# 3) 真机全量（约 105 分钟；每条能力一个干净会话）
python -m gxkit run --workdir <repo>\gxkit\_runs\g1
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
| 2026-10-24 | **28/28（v0.12，新增 iQ-R/FX5S 三条）** | 3564.6 s |
| 2026-10-24 | **28/28（v0.12，同一份代码第二次）** | 3593.5 s |
| 2026-10-24 | **28/28（v0.12，乱序跑 seed=7）** | 3556.3 s |
| 2026-10-24 | **32/32（v0.13，新增 FB 参数/结构体数组/多程序/iQ-R 软元件表）** | 4120.9 s |
| 2026-10-24 | **32/32（v0.13，同一份代码第二次）** | 4102.9 s |
| 2026-10-24 | **32/32（v0.13，乱序跑 seed=11）** | 4104.5 s |
| 2026-10-24 | **33/33（v0.14，含粘贴/保存校验重试）** | 4249.1 s |
| 2026-10-24 | **33/33（v0.14，同一份代码第二次）** | 4246.8 s |
| 2026-10-24 | **33/33（v0.14，乱序跑 seed=23）** | 4251.1 s |
| 2026-10-25 | **37/37（v0.15：编译器原话/工程校验/换语言/批量新建）** | 5326.4 s |
| 2026-10-25 | **37/37（v0.15，同一份代码第二次）** | 5321.9 s |
| 2026-10-25 | **37/37（v0.15，乱序跑 seed=31）** | 5332.1 s |
| 2026-10-25 | **42/42（v0.16：梯形图读/画/并联/应用指令/多梯级）** | 6302.2 s |
| 2026-10-25 | **42/42（v0.16，同一份代码第二次）** | 6327.1 s |
| 2026-10-25 | **42/42（v0.16，乱序跑 seed=47）** | 6302.8 s |

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

## 收尾策略：两轮同序 + 一轮乱序

| 轮次 | 命令 | 防什么 |
|---|---|---|
| 1 | `run --workdir ...\f1` | 基线 |
| 2 | `run --workdir ...\f2` | 时序运气（新会话、新时间轴） |
| 3 | `run --shuffle --seed <N>` | **顺序依赖 / 状态泄漏**（共享 workdir、骨架缓存、kill_stray 时机） |

第 3 轮是新增维度，不是"再测一遍同样的东西"：两轮全量已让每条能力各跑两遍，
第三遍同序收益很小；换顺序才能验证各能力之间有没有互相污染。
乱序种子记在 `result.json` 的 `seed`/`order` 里，可原样复现。

## v0.12 新增三条：多机型（iQ-R / FX5S）

探针 95 把新建工程对话框的系列/机型全列了一遍：

| 系列索引 | 名称 | 机型数 |
|---|---|---|
| 0 | MX控制器 | 10 |
| 1 | **RCPU（iQ-R）** | 28（R00…R32EN） |
| 2 | LHCPU | 4 |
| 3 | **FX5CPU** | 3（**FX5U / FX5UJ / FX5S**） |
| 4 | QCPU(Q模式) | 0（需另选机架） |
| 5 | LCPU | 0 |
| 6 | FXCPU | 0 |
| 7 | NCCPU | 1（R16NC） |

实测 RCPU/R00：`Unit=R00`、`UnitId=4609`，ST 粘贴→转换→存盘→读回源码全对（4 步、0 错）。
说明**能力链与机型无关**，只需把 series/model 参数化。

| 能力 | 读数 |
|---|---|
| `project.new_rcpu` | `unit=R00`、`unit_id=4609`、`is_st=true` |
| `project.new_fx5s` | `unit=FX5S`、`is_st=true` |
| `program.rcpu_roundtrip` | `unit=R00`、`source_matches=true`、`steps=4`、`errors=0` |

顺带纠正一个旧说法：**没有 FX5C 这条系列**，FX5 家族只有 FX5U / FX5UJ / FX5S。

### 乱序轮的实际顺序（seed=7）

`program.import_fb → project.meta → build.convert_all → program.import_xml →
program.read_st → batch.projects → datatype.member_access → inspect.devices →
project.reopen → build.error_detail → datatype.custom_members → build.locate_error_line →
label.multi_type → label.import_xml → project.new → program.paste_st →
inspect.source_map → build.program_check → project.diff → datatype.import →
program.rcpu_roundtrip → inspect.programs → project.new_fx5s → project.new_rcpu →
inspect.mil → datatype.member_var → project.save → program.import_fb_instance`

28 条全过，说明各能力之间**没有顺序依赖/状态泄漏**（共享 workdir、骨架缓存、
kill_stray 时机都经得起换序）。

## v0.13 新增四条（功能块参数 / 结构体数组 / 多程序 / iQ-R 软元件表）

| 能力 | 读数 |
|---|---|
| `program.import_fb_params` | `program_created=true`、`fb_created=true`、`call_in_source=true`、`errors=0`（162.7 s） |
| `datatype.struct_array` | `struct_stage_errors=0`、`array_access_in_source=true`、`errors=0`（148.9 s） |
| `program.multi_programs` | `both_created=true`、两段源码都在、`program_count=3`、`errors=0`（229.7 s） |
| `inspect.devices_rcpu` | `unit=R00`、`rows=3345`、`device_type_codes=3`、`has_type_35=true`（59.0 s） |

两条硬规矩（详见 PITFALLS 四十~四十四）：
1. `<Parameters>` 的**空组会让整份文档被静默丢弃**——空组一律不输出；
   此时 `errors=0` 是假象，必须同时看 `program_created`/`fb_created`。
2. `IN_OUT` 只能声明，传参或引用就报错；能力只做 IN / OUT / OUT_RETAIN。

另：iQ-R 的软元件模板确实和 FX5U 不同（3345 行 / 3 种类型码 vs 2935 行 / 2 种）。

### v0.13 的乱序轮（seed=11）

`build.locate_error_line → inspect.devices_rcpu → inspect.source_map → datatype.member_var → project.save → datatype.import → inspect.devices → program.read_st → project.diff → project.new → program.import_fb_instance → program.import_fb_params → program.import_xml → project.new_rcpu → project.new_fx5s → program.import_fb → label.import_xml → program.rcpu_roundtrip → inspect.programs → datatype.member_access → project.reopen → project.meta → program.paste_st → program.multi_programs → label.multi_type → build.convert_all → datatype.custom_members → inspect.mil → batch.projects → datatype.struct_array → build.program_check → build.error_detail`

32 条换序全过 → 无顺序依赖/状态泄漏。

## v0.14：手写骨架打通（不依赖 MELSOFT 样例）

定位过程：把"样例骨架"与"手写骨架"生成的 **同一份程序 XML 逐行 diff**，
唯一实质差异是局部变量上的 `<VariableRemark>`。去掉它以后：

| 读数 | 值 |
|---|---|
| `uses_manual` | true（`base.xml`） |
| `program_created` | true |
| `locals_found` | 2（LocBool / LocWord 都进 `LabelData`） |
| `errors` / `failed_stages` | 0 / `[]` |

规则：`Program`/`FunctionBlock` 的 `<Vars>` 里**不要** `VariableRemark`
（`GlobalVars` 保留）。`xmlgen.strip_local_remarks()` 统一处理，
能力 `xmlgen.manual_template` 守着这条。

这也意味着：`GXKIT_TEMPLATE`/缓存骨架不再是唯一出路——手写骨架可以独立工作。

### v0.14 的乱序轮（seed=23）

`datatype.member_access → project.diff → project.new_fx5s → label.import_xml → datatype.struct_array → program.import_fb_instance → build.program_check → batch.projects → build.convert_all → inspect.source_map → inspect.mil → inspect.programs → build.error_detail → inspect.devices → project.new_rcpu → program.rcpu_roundtrip → inspect.devices_rcpu → xmlgen.manual_template → program.read_st → build.locate_error_line → datatype.custom_members → program.import_xml → program.paste_st → project.save → program.import_fb_params → label.multi_type → datatype.import → datatype.member_var → program.import_fb → project.reopen → project.new → project.meta → program.multi_programs`

33 条换序全过 → 无顺序依赖/状态泄漏。

## v0.15 新增五条：编译器原话 / 改写已有程序 / 批量新建 / 工程校验 / 换语言

| 能力 | 读数 |
|---|---|
| `build.error_messages` | `pane_found=true`、`rows=1`、内容 `使用了未定义的标签。`、代码 `0x110E1A20`、分类 `转换程序`（117.1 s） |
| `project.check` | 结果页存在、`status_count=2`（`存在2个不同内容`）、表格首行 `程序文件 MAIN MAIN 不一致`（285.5 s） |
| `project.new_language` | ST/SFC/FBD 三个工程都建成、标题标记齐、`Unit=FX5U`（199.2 s） |
| ~~`program.edit_existing`~~ | 单次能过（263.1 s），但冷/热交替失败 → **撤出能力表**（见 UNSUPPORTED） |
| `batch.new_projects` | 3 个新工程同会话建成：都存在、源码逐字匹配、0 错（388.3 s） |

三条"换渠道"的结论也一并落地：

1. **编译器原话能拿到**——在「输出」面板，不在「转换结果」面板（后者转换失败时写着
   「对象未转换，因此无法显示转换结果。」）。
2. **SFC / FBD / IL 正文仍被静默丢弃**（探针 123）→ IEC XML 只认 ST。
3. **局部结构体成员名访问是机制级堵死**：又试"带/不带成员分配"两条，仍 `程序(...)转换中` 2 错（探针 144）。

### v0.15 的乱序轮（seed=31）

`datatype.member_access → program.import_fb_instance → inspect.devices_rcpu → program.import_xml → program.multi_programs → build.locate_error_line → program.import_fb_params → label.multi_type → project.meta → program.paste_st → project.reopen → datatype.import → xmlgen.manual_template → batch.new_projects → build.error_messages → datatype.member_var → datatype.custom_members → build.program_check → build.convert_all → project.diff → label.import_xml → inspect.source_map → project.new_rcpu → batch.projects → project.check → inspect.devices → inspect.programs → project.new_language → datatype.struct_array → program.rcpu_roundtrip → project.save → project.new_fx5s → program.import_fb → inspect.mil → program.read_st → build.error_detail → project.new`

37 条换序全过 → 无顺序依赖/状态泄漏。

## v0.16：梯形图（LAD）四条能力

先弄清 DSL，再逐层验证。下面每条都是真机读数。

| 能力 | 读数 |
|---|---|
| `program.write_ladder` | 2 触点 1 线圈，摘要 `-[ ]-a0@0,0 -[ ]-a1@1,0 -( )-a0@2,0`，0 错（185.4 s） |
| `program.write_ladder_parallel` | grid `12x2`、竖线 1、2 触点 1 线圈，0 错（185.4 s） |
| `program.write_ladder_appl` | 头里 `a:X:MOV:K_1:D`，1 触点 1 端子，0 错（177.9 s） |
| `inspect.ladder` | 往返：写 X0-X1→(Y0) 后离线读回 2 触点 1 线圈，0 错（185.6 s） |
| `program.write_ladder_multi` | 2 个正文块、3 触点 2 端子，0 错（207.3 s） |

探索过程中的关键读数（都进 `PITFALLS.md` 五十一~五十四）：

1. **`LadderBlocks.data` 是 `V1:` 文本 DSL**，`blocktype=0` 正文、`5` END；
   `e{s=ce{op=ct…}:pos=列,行}` / `op=cl`；`d{s=#:a=N}` 的 N 就是软元件地址（X0→0、X1→1、Y0→0）。
2. **F5/F7 不可靠**（同一像素一次成功一次报「执行位置不正确。」），改 **UIA Invoke 工具栏按钮**。
3. **并联必须最后插**：先插 OR 会被静默丢弃，并把「线圈」按钮弄成禁用态。
4. 真实产线工程（外部导入的 4 个 `.gx3`）用来对照 DSL：`ct` 的 `as=[as{vt=Abl}]` 恒定，
   线圈/应用指令的 `as` 多一段 `A16`，`c{s=#:v=1}` 是常数 K1。

### v0.16 的乱序轮（seed=47）

`batch.new_projects → program.import_fb → program.multi_programs → project.check → project.new_fx5s → program.paste_st → program.import_fb_params → datatype.import → xmlgen.manual_template → program.write_ladder_parallel → program.write_ladder → label.import_xml → project.meta → datatype.custom_members → project.reopen → build.error_messages → program.read_st → project.new_language → program.import_fb_instance → project.diff → datatype.struct_array → datatype.member_access → program.import_xml → build.program_check → program.rcpu_roundtrip → project.new → batch.projects → datatype.member_var → program.write_ladder_appl → project.new_rcpu → inspect.devices_rcpu → inspect.mil → inspect.devices → inspect.ladder → label.multi_type → inspect.source_map → build.locate_error_line → program.write_ladder_multi → build.error_detail → build.convert_all → project.save → inspect.programs`

42 条换序全过 → 无顺序依赖/状态泄漏（含梯形图五条排在项目/导入/标签各段之后）。
