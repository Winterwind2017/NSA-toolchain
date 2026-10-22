# 未打通 / 明确不做

每条都带证据；没有证据的不写在这里。

| 项 | 卡在哪 | 证据 |
|---|---|---|
| `project.check`（工程校验） | 菜单 `工程(P) → 工程校验(V)...` 存在，但校验结果面板没有稳定的读回口（结果在自定义面板里，未找到 UIA 文本或落盘文件） | 未验证，先不做 |
| `label.import_xml`（全局标签批量导入） | 通道可用：`工程 → 导入文件 → IEC61131-10 XML格式`，官方样例导入成功（`ConvertData` 生成、`Progress.txt` 出现 `全局标签(Global1)`），但样例里的结构体成员分配有 1 个 Error | `全部转换` 日志 `全局标签(Global1) 定义检查中... Error:1` |
| `program.import_xml`（用 XML 建程序） | 官方样例与自造最小 XML 都不建新程序：`Progress.txt` 里始终只有原有 `ProgPou`；程序体改用编辑器粘贴已解决同样需求 | `ConvertData/Progress.txt` 只见 `程序(ProgPou)` |
| `program.read_st`（读回 ST 源码） | `.gx3` 里 `_Project.txc` 是二进制（utf-8/utf-16/shift_jis 全部解码失败），程序体在 `.w3pa` 二进制分片里；SQLite `StBlocks.data` 只有 1 个字符 | 解包实测 |
| `online.write` / `online.read` / `online.monitor` | 需要真实 PLC 或内置模拟器；用户口径是"只做离线"，未验证 | 不做 |
| `ladder.*`（梯形图内容） | 梯形图编辑器是自绘控件，UIA 里没有单元格；只能靠菜单/快捷键操作，无法程序化写网络 | 不做（ST 已覆盖需求） |
| `cam.*` / `cae.*` | GX Works3 不涉及 | 不在范围 |
