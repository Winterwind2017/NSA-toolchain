# 未打通 / 明确不做

每条都带证据；没有证据的不写在这里。

| 项 | 卡在哪 | 证据 |
|---|---|---|
| `build.error_line`（行级错误定位） | `转换 → 转换结果`（Ctrl+Alt+O）调出来后，主窗里没有暴露文本的子控件（`EnumChildWindows` 只拿到 `Afx:*` 自定义视图，UIA 也读不到），`Progress.txt` 只给阶段级计数 | 探针 31/33：invoke 后无新窗口、主窗子控件无文本 |
| `project.check`（工程校验） | 该功能是**两工程比对**，不是"校验本工程"：不选"校验目标"就弹"未选择校验目标工程。"；选了之后是 diff 视图，未验证可读 | 探针 32：`工程校验` 对话框里点"校验" → modal `未选择校验目标工程。` |
| `program.read_st`（读回 ST 源码） | `.gx3` 里 `_Project.txc` 是二进制（utf-8/utf-16/shift_jis 全部解码失败），程序体在 `.w3pa` 二进制分片里；SQLite `StBlocks.data` 只有 1 个字符 | 解包实测 |
| `program.import_xml`（用 XML 建程序） | 官方样例与自造最小 XML 都不建新程序：`Progress.txt` 里始终只有原有 `ProgPou`；程序体改用编辑器粘贴已解决同样需求 | 探针 17/19/24 |
| `label.import_xml`（全局标签批量导入） | 通道可用（样例导入后 `Progress.txt` 出现 `全局标签(Global1)`），但样例结构体成员分配有 1 个 Error；未做稳定化 | 探针 26：`全局标签(Global1) 定义检查中... Error:1` |
| `online.write` / `online.read` / `online.monitor` | 需要真实 PLC 或内置模拟器；用户口径是"只做离线"，未验证 | 不做 |
| `ladder.write`（梯形图内容） | 编辑器是自绘控件，UIA 里没有单元格；只能靠菜单/快捷键，无法程序化写网络 | 不做（ST 已覆盖需求） |
| 同会话"新建下一个工程"的批量 | 已有路径的工程再 `Ctrl+N` 会状态漂移（另存为不弹框 / 标题丢路径 / 新建对话框打不开）；`batch.projects` 改成**同一工程连续粘贴 + 菜单另存为**绕过了这一点，所以"同会话新建 N 个不同工程"仍然不做 | 探针 35：同会话 `new_project` 连做 3 次，iter0/iter2 直接失败 |
