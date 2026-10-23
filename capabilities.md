# 能力索引（由 tools/sync_capabilities.py 生成，勿手改）

共 **21** 条已验证能力（内核 `gxkit 0.8.0`，commit `45c7ba6`，引擎 GX Works3 1.117.0.1，机型 FX5U，语言 ST，仅离线）。

| id | family | level | 说明 |
|---|---|---|---|
| `project.new` | project | L1 | 新建 FX5U + ST 工程 |
| `project.save` | project | L1–L2 | 另存为 .gx3（含读回校验） |
| `project.meta` | inspect | L1–L2 | 解包 .gx3：Config.xml + 条目数 |
| `program.paste_st` | program | L1–L3 | 把 ST 代码粘进编辑器并转换 |
| `program.read_st` | program | L1–L2 | 从 .gx3 读回 ST 源码（逐字比对） |
| `program.import_xml` | program | L2–L3 | 用 XML 新建程序（另起一个 PrgGen） |
| `program.import_fb` | program | L3 | 用 XML 建程序+功能块（带局部标签） |
| `program.import_fb_instance` | program | L3 | 用 XML 建功能块实例并调用 |
| `datatype.import` | datatype | L3 | 用 XML 建结构体（并用变量读回） |
| `datatype.member_var` | datatype | L3 | 结构体类型的变量（成员级软元件分配） |
| `datatype.custom_members` | datatype | L3 | 自定义结构体成员 |
| `inspect.source_map` | inspect | L2 | 步→源码坐标（Row/Col/StrLen） |
| `inspect.devices` | inspect | L1–L2 | 读 FX5U 系统软元件模板 |
| `inspect.mil` | inspect | L2 | 读编译后的 IL 文本 |
| `label.import_xml` | label | L2–L3 | 导入全局标签 XML 并读回 |
| `build.convert_all` | build | L1–L3 | 全部转换：从 Progress.txt 读错误数 |
| `build.program_check` | build | L2–L3 | 程序检查：读「无错误」判定文本 |
| `build.error_detail` | build | L2–L3 | 故意写错：定位错在哪个编译阶段 |
| `build.locate_error_line` | build | L3 | 二分法定位坏行（前缀问编译器） |
| `batch.projects` | build | L3 | 同会话批量出 3 个工程（各自 0 错） |
| `project.reopen` | project | L4 | 存盘→重开→步数仍在（L4） |

## 未打通

| 项 | 卡在哪 |
|---|---|
| `build.error_message` | 编译器原话：转换结果面板是自绘视图，读不到文本 |
| `label.non_bool` | WORD/DINT 标签导入未验证（只验证了 BOOL） |
| `project.check` | 工程校验是两工程比对，不是校验本工程 |
| `datatype.member_access` | 正文里按成员名访问结构体未通（成员已绑软元件） |
| `online.write` | 需要真实 PLC；用户口径只做离线 |
| `ladder.write` | 梯形图编辑器是自绘控件，无法程序化写网络 |
