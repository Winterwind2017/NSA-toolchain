# 踩坑记录（按发生顺序）

## 一、没有 API 这件事本身就是最大的坑

查过、确认无效的三条路：

| 路 | 证据 |
|---|---|
| COM | `HKCR` 下无 `Melco*`/`MELSOFT*`/`MXComp*` ProgID；MX Component 未安装 |
| 托管层进程内调用 | `Melco.GXW3.Controller.*` 是「契约 dll + `.Impl.dll` + `.Proxy.dll`」三件套，服务总线，没有宿主跑不起来 |
| 命令行 | 只有文件关联的 `GXW3.exe "%1"`，没有 `/import` `/export` `/build` 之类开关 |

→ 唯一可行：**Win32 消息 + UIA + 真实鼠标键盘**。

## 二、SetForegroundWindow 失败 → 所有按键"点了没反应"

Windows 只允许"刚启动的进程"或"用户点击过的窗口"抢前台。进程在后台时：

```python
u32.SetForegroundWindow(hwnd)   # 返回 0，窗口仍在后台
# 之后 Alt+P 不出菜单、Ctrl+N 不弹对话框 —— 看起来像"功能不可用"
```

**判据**：`u32.GetForegroundWindow() == hwnd`。修法（`win.activate`）：

```python
u32.ShowWindow(hwnd, 9)          # SW_RESTORE
u32.SwitchToThisWindow(hwnd, True)
u32.SetForegroundWindow(hwnd)
if u32.GetForegroundWindow() != hwnd:
    click(窗口标题栏中心)         # 点一下是最可靠的"合法前台"来源
```

**这条坑让"新建工程"反复失败了一整轮**，且症状表现为"对话框没出现"，极易误判成软件限制。

## 三、壳对话框里 cid 会撞车

`另存为` 是标准壳对话框：`cid=1148` 同时命中 `ComboBoxEx32` / `ComboBox` / `Edit`；
`cid=1` 同时命中 `FolderView` 列表和真正的"保存"按钮。

```python
_find_by_cid(dlg, 1148)               # 拿到 3 个句柄，第一个不是 Edit
_find_by_cid(dlg, 1148, cls="Edit")   # ✅ 必须带类名
_find_by_cid(dlg, 1, cls="Button")    # ✅ 必须带类名
```

症状：`WM_SETTEXT` 写进了 ComboBox，读回是空；`BM_CLICK` 点到了文件夹列表，文件没保存。

## 四、GX Works3 不给"未转换"的工程存盘

保存时弹：

> 全局标签处于未转换状态，因此无法将已编辑的系统标签信息登录至系统标签数据库。
> 登录至系统标签数据库时，请执行**全部转换**或转换后再保存工程。

所以顺序必须是 **粘贴 → 全部转换（Shift+Alt+F4）→ 保存**。
早期"导入 XML 后文件没变化"就是因为保存被这条拦住了（文件大小、mtime 全不变）。

## 五、`Ctrl+N` 不可靠，菜单也一样依赖前台

`Ctrl+N` 在新启动、无工程的状态下有时不响应；`Alt+P` 弹菜单同理（依赖前台）。
稳定做法是：**先 `activate()` 确认拿到前台，再用菜单项 invoke，失败才退回按键**。

## 六、UIA 子菜单项不能直接 Invoke

菜单是 `XTPPopupBar`（Toolkit Pro）。对未展开的菜单项调用 `Invoke` 会抛
`COMError -2146233083`。顺序必须是：

```python
alt_letter("p")                 # 先把菜单弹出来（出现 XTPPopupBar 窗口）
uia.invoke_menu_item("新建(N)")  # 再对 popup 里的 MenuItem Invoke
```

## 七、`.gx3` 是 ZIP，但里面的关键内容加密/编码

- `!!Config.xml`：纯文本，`<Config Unit="FX5U" UnitId="528" .../>` —— 机型判据来源
- `_Project.txc`：**二进制（无法按 utf-8/utf-16/shift_jis 解码）**
- `*.w3pa`：二进制分片，程序体在里面
- `*.db`：SQLite（`DEVICE_DATA`/`COMMENT_DATA`/`LabelData` 可直接读）
- `ConvertData/Progress.txt`：**纯文本编译日志**（最有用的判据）
- `.h/e/.t/`：内嵌 git 仓库

→ 结论：**读元信息与编译结果没问题；读/写程序源码不行**，所以程序内容走编辑器粘贴。

## 八、IEC 61131-10 XML 只能导入"标签类"

`工程 → 导入文件 → IEC61131-10 XML格式` 存在且能跑（官方样例导入成功，`ConvertData` 生成），
但：
- 全局标签可以导入（实测多出 `Global1`，还带 1 个 warning）；
- `<Program>` **没有**稳定地建出新程序（`Progress.txt` 里只出现原有 `ProgPou`）；
- 从零拼的最小 XML 也不建程序。

→ 程序内容不要依赖 XML，用编辑器粘贴；XML 留给"全局标签/结构体"这类批量数据。

## 九、每条能力一个会话，比共用一个会话稳

共用一个 GX Works3 时，"关工程 → 新建 → 保存"的状态漂移会让后续能力随机失败
（标题还带旧路径、保存被静默成另存、对话框不弹）。

改成"每条能力起一个干净进程"（+10 s 启动）后，全套稳定 6/6（v0.1 的六条）。

## 十一、同会话"再新建一个工程"一定会漂

`batch` 最初想在一个会话里连做：新建 → 粘贴 → 转换 → 另存为 → 再新建……
实测第 0 轮就失败（另存为对话框里没有文件名输入框），第 2 轮连新建对话框都打不开。
原因还是状态漂移：工程一旦有路径，`Ctrl+S` 变成静默保存，标题也可能丢路径。

**真正可行的批量**：不要新建，**同一个工程里连续改代码 → 转换 → `工程 → 另存为`**。
`另存为` 即使工程已有路径也会弹对话框，所以每轮都能落到新文件。
`batch.projects` 就是这样做的：3 个变体 129.7 s，三个文件大小各不相同（长度递增的代码）。

## 十二、"工程校验"不是"校验本工程"

`工程 → 工程校验(V)` 打开的是**两工程比对**：左边"编辑中数据"，右边必须选"校验目标工程"，
不选就弹"未选择校验目标工程。"。

想要"这个工程对不对"，正确入口是：
- `转换 → 全部转换`（编译，判据在 `Progress.txt`）
- `工具 → 程序检查`（指令/双线圈/软元件检查，判定文本 UIA 可读：`程序检查已完成。无错误。`）

注意 `程序检查` 要求工程**已转换**，否则弹"程序中存在未转换的梯形图，因此无法继续执行处理。"

## 十三、XML 的 `GlobalVars` 放错位置会被**静默忽略**

导入 IEC 61131-10 XML 时，标签表必须放在：

```
Project/Instances/Configuration/GlobalVars
```

放 `Types/GlobalNamespace/GlobalVars`、或 `Instances/GlobalVars`（漏一层 `Configuration`），
导入照样"成功"、`Progress.txt` 里**连"全局标签(Global1)定义检查中"这一步都不出现**，
`LabelData` 行数一行不变——没有任何报错。

## 十四、克隆样例变量后必须改"行号"

以官方样例的 `<Variable>` 为模板克隆三条，只改 `name`/`Address` 时，**只有第一条会进工程**
（`LabelData` 只 +7 行，只出现 `LBL_A`）。

把 `<VariableLineNumber number="...">` 改成唯一编号、注释/备注换成各自的文本之后，
三条全部落地（`54 → 75` 行，`LBL_A/B/C` 都在）。所以"少导入"不等于"XML 写错"，
往往是**键重复被去重**。

## 十五、行级错误：编译器不给行号，但可以"问"出来

编译失败时 `T_Step` 是空的（没有步就没有源码坐标），`转换结果` 面板是自绘视图读不到。
能拿到的事实只有"这段代码有 N 个错误"。于是用**前缀二分**：

```
lines[0:k] 通过、lines[0:k+1] 失败  →  第 k+1 行是坏行
```

8 行程序、坏行在第 5 行 → `k=8 失败 / k=4 通过 / k=6 失败 / k=5 失败`，4 次转换定位到第 5 行。
**前提**："错在前缀里就会一直错"，这对编译错误成立；同时每次都要存到**新文件名**，
因为 GX Works3 还占着上一个文件（`PermissionError: WinError 32`）。
**确定性的价值高于启动成本**。

## 十、模拟器/在线一律没碰

用户口径是"只做离线"。`在线(O)` 菜单里的写入/读取/监视需要真实 PLC 或内置模拟器，
未验证，不当成能力。

## 十六、"每个程序一套 SQLite"——只读第一个会漏掉整个程序

`.gx3` 里不是一份 `*_STDB.db`，而是**每个程序一份**（STDB / StepInfo / MilDB 各一套）。
一开始 `_db()` 只 `sorted(glob)[0]`，于是：

- `program.read_st` 读到的永远是 `ProgPou`（空程序 `;`）；
- 导入 XML 建出的 `PrgGen` **明明在工程里**，却读不到它的源码；
- 结果是"导入成功但读不到"这种假失败。

改成遍历全部 `*_STDB.db` 之后，`PrgGen` 的源码（UTF-16LE 存的 TEXT）才露出来。
顺带：StepInfo 的 `BlockID` 是 `{GUID}`、STDB 的 `id` 是 `_guid/<guid>`，
要靠 `_block_key()` 归一化（去 `_guid/`、去花括号、小写）才能把"步"和"源码"对上。

## 十七、XML 建程序：要 Resource/ProgramInstance，还要删 Vars

`<Program>` 单独存在**不会**建出程序；必须同时在

```
Project/Instances/Configuration/Resource/ProgramInstance[@name, @typeName="pou", @evaluationOrder]
```

里声明一个同名实例（样例里 `Program1` ↔ `Resource name="Main"`）。

第二件事：样例的 `Program1` 带 `<Vars>`，引用 `FBPou1`/`Struct1`/`TIMER` 等类型，
把这些类型删掉后必须**把 `<Vars>` 一起删掉**，否则导入报错/不建程序。
正文只用设备软元件（`B0`/`W0`）就干净了。

## 十八、程序体比较要"去空白"

导入后的源码会多出空行（实测 `B0 := NOT B0;\r\n\r\nW0 := W0 + 1;`），
直接字符串相等会判失败。比较时统一 `"".join(text.split())`（去掉所有空白）。

## 十九、导入别重试——它会真的再建一个程序

`program.import_xml` 第一版"判据没过就再导一次"，结果工程里出现 `PrgGen` 和 `PrgGen_2`
（GX Works3 自动改名）。导入是**非幂等**操作：判据错了要修判据，不要重试导入。

## 二十、Alt 系列用 PostMessage，Ctrl 系列必须用 SendInput

这一条是**用半晚上换来的**，两个方向都反直觉：

- `Alt+P` 用 `keybd_event/SendInput` 时，**有时候根本到不了窗口**（菜单不弹、
  接着 Ctrl+N 也不弹新建对话框，看起来像"软件坏了"）。改成
  `PostMessage(hwnd, WM_SYSKEYDOWN, VK_MENU ...)` + `WM_SYSKEYDOWN('P')` 之后 **2/2 稳定**。
- 反过来，`PostMessage` 投递的 `Ctrl+S` / `Ctrl+N` 会被 MFC 的加速键表**忽略**，
  必须用真实按键（`SendInput`）。

所以 `Session._alt()` 走 PostMessage，`Session._ctrl()` 走 SendInput。

## 二十一、窗口会以 135×37 "折叠"启动

这种状态下菜单栏**根本不存在**（UIA 找不到菜单项），`Ctrl+N` 也不弹对话框。
`ensure_size()` 会 `SW_RESTORE`，仍偏小就 `MoveWindow` 到 1280×900。
另外这个句柄可能**已经失效**（`GetWindowRect` 抛 `pywintypes.error 1400`）——
踩过：这个异常让整个 run 卡在第一项上 30 分钟。现在 `ensure_size` 返回 `invalid=True`，
`_focus()` 会重新取主窗。

## 二十二、`Ctrl+S` 在新建工程后经常不弹"另存为"

焦点还在某个控件里的时候，`Ctrl+S` 静默失败、不弹对话框，于是"存盘"变成空操作
（文件根本不存在）。现在 `save_as()` **菜单优先**：

```
工程(P) ─ Alt+P(PostMessage) → UIA invoke 「另存为(A)」 → #32770 出现 → 填 cid=1148 → 点 cid=1
```

失败才退回 `Ctrl+S`。

## 二十三、上一轮进程没退干净，下一轮会"卡在已有实例"

每条能力之间会 `taskkill /IM GXW3.exe /T`（`win.kill_stray()`）。
否则下一条启动后停在"已有实例"状态：窗口在、菜单不响应、新建工程对话框永远不弹。

## 二十四、XML 里 Program 必须排在 FunctionBlock 前面

把 <FunctionBlock> 插到 <Program> 之前，整份导入会被**静默忽略**：
导入"成功"、0 错、工程里连程序都没建、Progress.txt 只有 ProgPou。
把它挪到后面，同样的内容立刻生效（程序(PrgFB) 出现、FB 正文进 STDB）。

样例的顺序就是 Documentation, AddData, Program..., FunctionBlock..., Function, DataTypeDecl，
**照抄顺序**比自己排更保险。

## 二十五、功能块要删掉 <Parameters>

样例的 FB 带 <Parameters>（Inout/Input/Output 四组），里面引用 b1_vio 之类的样例变量。
保留它、同时把 Vars 换成自己的变量 → 整份导入同样被静默忽略。
删掉 <Parameters>、Vars 只留一块（private），就正常了。

另外 FB 的样例变量只有 VariableComments、没有 VariableLineNumber，
补一个唯一行号更稳（_ensure_line_number）。

## 二十六、功能块不会出现在 Progress.txt 的"程序(...)"清单里

program_names() 只能抓到 程序(PrgFB)；功能块**没有独立条目**。
判定 FB 是否建出来要看两处：
* 多出一份 *_STDB.db，内容是 FB 的正文；
* LabelData 里出现 FB 的变量名（如 FB_Bool）。

## 二十七、结构体的成员必须是样例那一套

`DataTypeDecl` 能导入（导航树里会出现 `StructGen タイトル Struct1`），
但**不要重建或裁剪 `<Member>`**：一旦自己拼成员（哪怕只有一个 BOOL），
整份导入会被**静默丢弃**——连程序都不建、0 错、`Progress.txt` 里只有 `ProgPou`。

结论：结构体按"样例原样 + 只改类型名"导入；成员名改动属于未验证区。

## 二十八、结构体类型的变量仍会报错

`S1 : StructGen` 这种局部标签能够落库（`S1` 出现在 `LabelData`、结构体也在导航树里），
但 `局部标签(PrgS4)定义检查中` 会有一条 **Error:1**——大概需要成员级软元件分配
（样例全局标签里的 `VariableStructDeviceAssignment`）。所以判定"结构体建出来了"
要换判据：**UIA 导航树里出现结构体名**，而不是"有变量能用它"。

## 二十九、`DataTypeDecl` 在 `.gx3` 里搜不到明文

导入结构体后，`StBlocks`/`LabelData` 都没有结构体名；在工程库里搜类型名与成员名
（utf-8 / utf-16）都是零命中。**唯一可靠的读回口是 UIA 导航树**：
`uia.find_names(hwnd, "StructGen")` → `StructGen タイトル Struct1`。

## 三十、导入"静默什么都没进"时可以安全重试

导入偶发整份被忽略（对话框确认没落到），表现是工程里**一点变化都没有**。
此时重试是安全的；但**一旦检测到目标程序出现就绝不能重试**（导入非幂等，
会得到 `PrgGen_2`）。`_import_verified()` 就是按这个规则写的。


## 三十一、UserDefinedTypeSpec 的 <AddData> 必须留在成员后面

这是自定义结构体成员的**唯一**卡点，也是它骗了我好几轮的原因：
重建成员时我用 spec.remove(member) 再 spec.append(new)，样例里那个**排在最后的
<AddData> 就被推到了最前面**，于是整份导入被静默丢弃——0 错、连程序都不建、
导航树里也没有结构体。

对照实验（探针 73）：同一份 XML，只把 <AddData> 挪回最后，立刻导入成功。
所以"结构体成员必须原样"那条旧结论是**错的**，真正的规则是**元素顺序**：
UserDefinedTypeSpec = Member × N，然后 AddData。

## 三十二、结构体名字上的 	itle 不会被改

导航树显示 StructCust タイトル Struct1——类型名改了，DataTypeProperties 里的
	itle 还是样例的。这只是显示文案，不影响导入。


## 三十三、按成员名访问结构体，必须用**全局**标签

同一个结构体，变量放哪儿决定了能不能按成员名访问：

| 放法 | 正文 X.MyBool := NOT X.MyBool; |
|---|---|
| 程序局部标签（Program/Vars 里的 S1 : StructCust） | 程序(...)转换中 **报错** |
| **全局标签**（Instances/Configuration/GlobalVars 里的 GS1 : StructCust） | **0 错** |

全局结构体标签还要带成员级软元件分配（和局部的一样），并且**不要 Address**。
导入后 Progress.txt 会多出一个阶段：结构体(<类型名>)的定义检查中——正好当判据。


## 三十四、非 BOOL 标签的初值必须与类型匹配

克隆 BOOL 模板做 WORD/DWORD 标签时，<InitialValue><SimpleValue value="FALSE">
会留在里面——类型是 WORD、初值是 FALSE。结果：**一个标签都不落地**
（Progress.txt 里连 全局标签(Global1)定义检查中 都不出现，rows 停在 54）。

改成按类型给初值（BOOL→FALSE、WORD/DWORD/INT→0）之后，三个标签全部落地（54→75）。

## 三十五、别给 <Variable> 加自定义属性

我给标签变量加了一个 	emplate="variable" 属性当标记，结果整份标签导入被忽略。
XML 里任何不认识的属性都可能让解析器整段放弃——要带元信息就放在代码里，别写进 XML。

## 三十六、局部结构体变量按成员名访问：五条路都不通

| 试法 | 结果 |
|---|---|
| 局部标签 private + S1.MyBool := NOT S1.MyBool; | 程序(...)转换中 2 个错 |
| 局部标签 **public** + 同上 | 2 个错 |
| 局部标签 private + S1.MyBool := TRUE; | 1 个错 |
| 局部标签加**整体** <Address> | 整份导入被丢弃 |
| 结构体 DataTypeDecl 放到 Program **前面** | 整份导入被丢弃（顺序反了） |

结论：这个导入器里**局部**结构体标签不支持成员名访问；
**全局**结构体标签可以（见 datatype.member_access，0 错）。要按名字访问就提到全局。

## 三十七、XML 骨架不要"每次运行时去读 MELSOFT 的样例"

早期 `xmlgen` 每次生成都以安装目录里的 `Sample.xml` 当骨架——MELSOFT 一升级换样例，
整套生成器就可能整批失效，而且**失效方式是静默的**。

现在：首次运行把样例复制到 `%LOCALAPPDATA%/gxkit/skeleton.xml` 并记下 sha256，
之后都读缓存；指纹变了自动重建；`GXKIT_TEMPLATE=<文件>` 可以完全绕开安装目录。

## 三十八、手写骨架卡在"局部标签"——真因是 `<VariableRemark>`（已解决）

一开始以为手写骨架缺了什么结构，最后靠 **逐行 diff 两份生成的 XML** 定位：
唯一实质差异是手写骨架的局部变量带了 `<VariableRemark>`。去掉之后
`LocBool`/`LocWord` 立刻落地、转换 0 错（探针 108 diff + 109 实测）。

规则：**Program / FunctionBlock 的 `<Vars>` 里不要 `<VariableRemark>`**；
`GlobalVars` 的 remark 保留（标签导入那边验证过是有用的）。
`xmlgen.strip_local_remarks()` 统一处理，能力 `xmlgen.manual_template` 守着这条。

## 三十八·旧、手写骨架卡在"局部标签"

我们自己写的 `templates/base.xml`（`use_manual_template()` 可切）能让
程序、全局标签、全局结构体+成员名访问全部导入成功；但**局部标签不落地**
（locals_found=0，随后 `程序(...)转换中` 报 2 错）。

排除过的因素：`PouProperties title`、`AddData` 内部顺序、去掉 `VariableRemark`/
`InitialValue`、补 `BodyProperties`/`FbPouProperties`。FB 那条因此通了，局部标签没有。
要真正自给自足，得继续做"逐元素 diff 二分"，记在 `docs/EXPAND_BACKLOG.md` 第 6 条。

## 三十九、叫停全量跑：`job_kill` 只杀外层，真正的运行器还在跑

全量套件是 "pwsh → python -m gxkit run → 每条能力 taskkill/启动 GXW3"。
对后台任务 `job_kill` 只终止**外层 pwsh**，`python` 子进程会继续按清单一条条跑，
表现就是"说了暂停，GX Works3 还在自动开窗口"。

正确收尾：

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*gxkit run*' } |
  ForEach-Object { & taskkill /T /F /PID $_.ProcessId }
Get-Process GXW3 -ErrorAction SilentlyContinue |
  ForEach-Object { & taskkill /T /F /PID $_.Id }
```

杀完要复查：`(Get-Process GXW3).Count` 与 `(Get-Process python).Count`。
注意别误杀无关的 python（本机常驻 SolidWorks-MCP 等 MCP 服务），
用命令行里是否含 `gxkit run` 来过滤。

## 四十、功能块 `<Parameters>`：空组会让整份文档被静默丢弃

带参数的 FB 需要 `<Parameters>`，里面可以有四组：
`InoutVars` / `InputVars` / `OutputVars retain="false"` / `OutputVars retain="true"`，
顺序固定。**但空组不能输出**——`<InoutVars/>` 只要出现（哪怕没有变量），
整份导入就被静默丢弃（程序与 FB 都不建、`errors=0`）。

判定陷阱：这种"什么都没进"时转换阶段根本不会列这两个 POU，所以 `errors=0` 是**假象**，
必须同时检查 `program_created` / `fb_created`。

## 四十一、IN_OUT 参数只能声明，不能传参或引用

`<InoutVars>` 里声明一个变量没问题（正文不引用、调用不传它就 0 错）；
一旦在调用里写 `InstFB(vio := B0)` 或正文里用 `vio`，
就变成 `局部标签(FB)定义检查中` 1 错 + `程序(...)转换中` 2~4 错。
能力只做 IN / OUT / OUT_RETAIN。

## 四十二、调用必须给全输入

FB 的输入参数如果没有初值，调用时漏传就会 `程序(...)转换中` 报 2 错。
给输入加 `<InitialValue>`，或调用时把输入全给上。

## 四十三、结构体数组成员要 `InstantlyDefinedType/ArrayTypeSpec`

    <Type>
      <InstantlyDefinedType xsi:type="ArrayTypeSpec">
        <BaseType><TypeName>BOOL</TypeName></BaseType>
        <DimensionSpec dimensionNumber="1"><IndexRange lower="0" upper="3"/></DimensionSpec>
      </InstantlyDefinedType>
    </Type>
    <Address address="B10"/>        ← 数组基地址

成员分配里给数组一个基地址（`<Member name="Arr" address="B10"/>`），
正文就能写 `GS1.Arr[0]`。

## 四十四、同一工程再导一次全局标签会撞名

第二次导入带 `GlobalVars` 的文档时，`全局标签(Global1)` 会变成 `Global1_2`
并被报定义错。**每个工程只导一次全局标签**；程序可以多次导入。

## 四十五、「转换结果」面板在转换失败时是空的

截图证据：面板写着「对象未转换，因此无法显示转换结果。」
**编译器原话在「输出」面板**：表头 `No./结果/数据名/分类/内容/错误代码`，
一行示例 `1 | Error | ProgPou | 转换程序 | 使用了未定义的标签。 | 0x110E1A20`。
读法：`DataGrid`(50007) 下按文档顺序 `FindAll` 所有 `DataItem`(50020)，每 6 个切一行；
`GridPattern`/`TablePattern` 在这个控件上都拿不到（NULL COM pointer），tree walker 也看不到子节点。

## 四十六、文件对话框别用 SetWindowText

「工程校验」选目标工程时，`SetWindowTextW` 打到的是"文件类型"那个 Edit，
文件名框仍空 → 点校验弹「未选择校验目标工程。」。
正解：按类名找**最宽且位于对话框下半部**的 `ComboBox`，点进去 → `Ctrl+V` 粘贴路径 → 回车。

## 四十七、`SendMessage(BM_CLICK)` 会同步阻塞

点「校验」用 `SendMessageW(btn, BM_CLICK)` 会让探针卡死（处理函数跑完才返回，期间还有模态窗）。
改用鼠标点按钮中心（异步），并在按钮前后留 6–10 秒。

## 四十八、导航树要双击「程序本体」子行，且行矩形有 ~13px 偏差

双击程序名前那一行不会打开编辑器；要双击它下面的「程序本体」。
而且 UIA 报的行矩形与视觉位置差 ~13px（probe131 在 +13 处才点开），
所以按 `0/6/12/18/-6` 做垂直扫点，用标题里的 `[ST]` 当成功判据。

## 四十九、工程语言是新建对话框里的一个下拉

`语言` 下拉 = `梯形图 / ST / SFC / FBD / 不指定`。选 SFC/FBD 建出来的工程标题分别是
`[PRG] [SFC]`、`[PRG] [FBD/LD]`，都能存盘、Unit 仍是 FX5U（正文怎么写是另一回事）。
顺带纠正：`FX5C` 只是 `FX5CPU` 在下拉里被截断显示，不是另一个系列。

