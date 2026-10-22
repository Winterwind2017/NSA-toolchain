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
**确定性的价值高于启动成本**。

## 十、模拟器/在线一律没碰

用户口径是"只做离线"。`在线(O)` 菜单里的写入/读取/监视需要真实 PLC 或内置模拟器，
未验证，不当成能力。
