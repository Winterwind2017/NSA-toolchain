# 未打通 / 明确不做

每条都带证据；没有证据的不写在这里。

| 项 | 卡在哪 | 证据 |
|---|---|---|
| `build.error_message`（编译器的原话） | `转换 → 转换结果`(Ctrl+Alt+O) 调出来后，主窗里只有 `Afx:*` 自绘视图（`EnumChildWindows` 与 UIA 都读不到文字）；`Progress.txt` 只给阶段级计数 | 探针 31/33 |
| `label.non_bool`（WORD/DINT 标签） | 当前只验证了 BOOL；把 `TypeName` 改成 WORD 时只有一个标签落地，未验证是否类型相关 | 探针 42（`LBL_A` 出现、`LBL_B/C` 缺失） |
| `project.check`（工程校验） | 该功能是**两工程比对**，不是"校验本工程"：不选"校验目标"就弹"未选择校验目标工程。" | 探针 32 |
| `datatype.local_member_access`（**局部**结构体变量按成员名访问） | 全局结构体标签已通（见 `datatype.member_access`）；同样写法放在程序局部标签上，`程序(...)转换中` 仍报错 | 探针 66 / 75 |
| `online.write` / `online.read` / `online.monitor` | 需要真实 PLC 或内置模拟器；用户口径是"只做离线"，未验证 | 不做 |
| `ladder.write`（梯形图内容） | 编辑器是自绘控件，UIA 里没有单元格；只能靠菜单/快捷键，无法程序化写网络 | 不做（ST 已覆盖需求） |
| 同会话"新建下一个工程"的批量 | 已有路径的工程再 `Ctrl+N` 会状态漂移（另存为不弹框 / 标题丢路径 / 新建对话框打不开）；`batch.projects` 改成**同一工程连续粘贴 + 菜单另存为**绕过了这一点 | 探针 35 |
| 行级错误"编译器原话" | 没有可读的错误消息；`build.locate_error_line` 用**前缀二分问编译器**得到行号，属于推断而非原文 | 探针 44 |
| `xmlgen.self_contained_template`（完全不用 MELSOFT 样例的骨架） | 手写骨架能导入程序/标签/全局结构体，但**局部标签不落地**（locals_found=0 + 转换 2 错）；已排除 title/顺序/Remark/InitialValue/BodyProperties 五个因素 | 探针 79 + tc1-tt3 |
| `ladder.import_xml` / `fbd.import_xml`（IEC XML 里的 LD / FBD 正文） | **XML 导入通道只收 ST 正文**。9 次实验全部被**静默丢弃**（0 错、程序不建）：标准 LD（触点+线圈）、最小 `<LD/>`、`xsi:type=Ladder`、三种 PouProperties、属性最小化、只放母线、XSD 序列顺序（母线在前）、以及 IL 正文。同文档换成 ST 立即成功（对照组）。另：没有别的入口 ——「打开其他格式文件」只支持 GX Works2/3、PX Developer、GX Developer；「数据操作」没有导出；XSD 未随装；官方 Sample.xml 只有 ST | 探针 82/85/86/90/91/92/94 |
