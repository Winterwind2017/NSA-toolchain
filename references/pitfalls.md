# 坑（每条都踩过）

## 通道与命令

- **菜单不是 Win32 菜单**：`GetMenu(hwnd)` 返回 NULL，命令走 `WM_COMMAND` + 数字 ID。
  查 ID 用 `autoshopkit commands --search <关键词>`，别按名字猜偏移。
- **同一实例只能一套测试**：两个套件并行会报 `COMError (-2147220991, '事件无法调用任何订户')`，
  看着像程序崩溃，其实是抢同一个 AutoShop。串行跑。
- **模态框会反复弹**：工程引用了本机缺失的 EtherCAT ESI 时，编译/导入/导出每发一次命令就弹一次；
  `_dismiss_all()` 只关当前那一个。此时这些命令不可用，但读树、读文件仍然可以。

## 树

- `TVITEMW` 是 **40 字节**手打包结构（不是 64 位 ctypes 的默认布局），隔着进程读必须自己拼。
- **折叠的节点拿不到 rect**：`TVM_GETITEMRECT` 返回的是邻居的矩形；先 `TVM_EXPAND` 父节点。
- **双击文件夹行只是展开**：`open_tree_child` = 展开父 → 单击 → 核对 `TVGN_CARET` → 双击；
  成功判据是出现新文档，不是"点了两下"。
- **H5U 的工程树是 cid=2**（cid=1 是器件目录，877 项）。用 `app.tree()`（按根文本选），
  别自己按 cid 取，否则你会拿到 877 行的器件清单还以为工程是空的。

## 视图与编辑器

- **"查看→指令表"的 ID 是 32883**（`切换为指令列表编辑器`），不是 32867。
  32867/32868/32869 是 SFC 的「添加并行分支 / 并行汇合 / 梯形图块」——用错 ID 会静默无效，
  在 SFC 文档上还会真的插进一个分支。
- **H5U 没有指令表编辑器**：程序存 `.LD`，语言只有 `梯形图(LD)`/`结构化文本(LiteST)`
  （资源表里就这两条，没有 IL）。实测在无 EtherCAT 阻塞的 H5U 副本上发 32883：
  `Scintilla` 仍为 0、无新文档、`program_il()` 为空。
- 所以 H5U 的 IL 只能从编译产物读（`il_log.log` / `Compile/*.compile`），读完不能反写。
- 想判断"当前这台能不能写程序"，看 `doctor.il_editor`：**H3U 打开程序就有 Scintilla**，
  H5U 永远没有。

## 程序编辑

- **`SCI_SETTEXT` 是假的**：它只改缓冲区，切文档/保存就丢。必须真全选（Ctrl+A）+ 剪贴板粘贴。
- 写入只接受 **LF**；CRLF 会在指令表里留下一堆空行，编译报"无法识别"。
- H5U 没有指令表编辑器：`查看→指令表` 无效，`Scintilla` 计数为 0，只能读编译产物 `il_log.log`。
- 梯形图是自绘画布（无 UIA 子元素），盲点等于赌博，别做。

## 输出窗与诊断

- 输出窗是**自绘 `ListBox`**：`LB_GETTEXT` 返回四个 NUL，取不到文本。
  文本靠 Frida hook `DrawTextW` 抓；`doctor` 里 `output_pane=true` 才说明 hook 在。
- 编译"跑完了"不等于"读到了"：先确认输出窗有内容，再解析。
- 编译成功时进程退出码也可能是 1（AutoShop 的老毛病），用 `summary` 判断。

## 网格（符号表 / 监控表）

- 单元格编辑器类名是 `ATL:<hash>`，**hash 因控件而异**，不能写死；要按 `ATL:` 前缀 + 父窗口限定。
- comtypes 找不到时会返回**真值 NULL 指针**（`bool(ptr)` 为真但 `.value` 崩）；每次都要查 `.value`。
- 网格没有剪贴板导出，只能逐格读（点格 → F2 → 取文本 → Esc）。

### 符号表只有 19 行，超过就必须"导入Excel"

- **默认空表只有 19 个数据行**。`add_symbol(row=n)` 在 `n>=19` 时**不会建行**：
  点击位置落到表格外，随后所有写入**折回第 1 行反复改写**——看起来"写成功了"（返回值 True），
  实际前 19 行之外全是垃圾。2026-10-26 因此白做 74 行。
- **不要试图用 UI 建行**：在末尾行按回车确实会加一行（人工操作有效），但自动化里
  `Enter`/`Tab` 都不提交单元格编辑（见 RECON §9），逐格+建行的回路没跑通；整块粘贴
  （Ctrl+V，TSV）实测**一行都进不去**（读回 0 行）。
- **正解：符号表自带 `导出Excel`(33182) / `导入Excel`(33183)**，把 `WM_COMMAND` 投给
  **frame** 就能唤起（RECON 里"文档级 id 投框架无效"只对 33xxx 工具条 id 成立）。
  模板：第 0 行 `(空) | 符号 | 地址 | 注释`，数据行 `序号 | 符号 | 地址 | 注释`。
  用 xlwt 写 .xls（BIFF8）→ 导入 → `save_project` → `symbols(source="file")` 核对。
  现成脚本：`scripts/import_symbol_table.py`。实测 74/74，缺 0 多 0。
- **符号名被截断到 8 字符**（`SB_SAFE_DOOR` → `SB_SAFE_`），且截断后可能重名；
  导入前必须自己规范化 + 去重，别指望报错。
- **文件对话框的"文件名"输入框 cid 不同**：`另存为` 是 `1001`，`打开` 是 `1148`
  （两者都是 `Edit`，且在 `ComboBoxEx32 → ComboBox → Edit` 里嵌套一层，要递归找）。
  按 1001 硬找 → 找不到 → 模态框挂在屏幕上不关，后面所有文档操作全部失效。
- **`scintilla()` 不是"当前处于指令表模式"的判据**：H3U 的程序文档**天生就有** Scintilla，
  全新启动、标题是 `[MAIN]` 时它就是 True。写程序报 `no instruction-list editor in the
  active document` 时，真实原因通常是**活动文档不是 MAIN**（比如刚导完符号表，活动页是符号表），
  先 `activate_document("MAIN")`；不要靠重复发 `view_il` 或 `scintilla()` 猜。

## 文件

- **`.hcp` 打开期间独占锁**：读文件前 `stop`，否则 `PermissionError`。
- `.hcp` 不是二进制结构，是 **UTF-16LE XML** + 位置相关变换；按二进制去猜会白费很多时间
  （奇数偏移恒为高字节 0，看起来像 22 字节周期掩码）。
- `.LD` 里**没有坐标**：元件记录是 `<u32 a><u32 b><u16 kind><u8 len><text>`，`a`/`b` 是图链接，
  绘制由拓扑推导。想"算出元件在屏幕上的位置"是死路。
- 部件文件的 0x1f 处那 8 字节 `clQobtqa` 是 `EncryptArithmetic(8 个 0)` 的产物，
  不是魔数常量（所以任何二进制里都搜不到它）。

## 环境

- **DPI**：内/外进程 awareness 不一致时 UIA 给物理矩形、SendInput 用逻辑坐标，差 1.5 倍，
  表现为"点偏了"。先统一 awareness。
- `project_path` / `project_name` 是 **property**，不是方法（`app.project_path()` 会 TypeError）。
- 客户工程**只读副本**：所有写入在 `sandbox/` 里做，仓库里永远见不到客户路径。
