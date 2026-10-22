# 未打通 / 明确不做

每条都带证据；没有证据的不写在这里。

| 项 | 卡在哪 | 证据 |
|---|---|---|
| `build.error_message`（编译器的原话） | `转换 → 转换结果`(Ctrl+Alt+O) 调出来后，主窗里只有 `Afx:*` 自绘视图（`EnumChildWindows` 与 UIA 都读不到文字）；`Progress.txt` 只给阶段级计数 | 探针 31/33 |
| `label.non_bool`（WORD/DINT 标签） | 当前只验证了 BOOL；把 `TypeName` 改成 WORD 时只有一个标签落地，未验证是否类型相关 | 探针 42（`LBL_A` 出现、`LBL_B/C` 缺失） |
| `project.check`（工程校验） | 该功能是**两工程比对**，不是"校验本工程"：不选"校验目标"就弹"未选择校验目标工程。" | 探针 32 |
| `program.import_fb`（带 FB/FUN/局部标签的程序） | 只验证了"一个空标签的 ST 程序"；带 `<Vars>` 的程序会引用 FBPou1/Struct1/TIMER 等类型，未验证能否一并导入 | 探针 51（删掉 Vars 才成功） |
| `online.write` / `online.read` / `online.monitor` | 需要真实 PLC 或内置模拟器；用户口径是"只做离线"，未验证 | 不做 |
| `ladder.write`（梯形图内容） | 编辑器是自绘控件，UIA 里没有单元格；只能靠菜单/快捷键，无法程序化写网络 | 不做（ST 已覆盖需求） |
| 同会话"新建下一个工程"的批量 | 已有路径的工程再 `Ctrl+N` 会状态漂移（另存为不弹框 / 标题丢路径 / 新建对话框打不开）；`batch.projects` 改成**同一工程连续粘贴 + 菜单另存为**绕过了这一点 | 探针 35 |
| 行级错误"编译器原话" | 没有可读的错误消息；`build.locate_error_line` 用**前缀二分问编译器**得到行号，属于推断而非原文 | 探针 44 |
