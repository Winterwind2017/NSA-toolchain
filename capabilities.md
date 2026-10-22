# 能力索引（由 tools/sync_capabilities.py 生成，勿手改）

共 **9** 条已验证能力（内核 `gxkit 0.2.0`，commit `21c0bc3`，引擎 GX Works3 1.117.0.1，机型 FX5U，语言 ST，仅离线）。

| id | family | level | 说明 |
|---|---|---|---|
| `project.new` | project | L1 | 新建 FX5U + ST 工程 |
| `project.save` | project | L1–L2 | 另存为 .gx3（含读回校验） |
| `project.meta` | inspect | L1–L2 | 解包 .gx3：Config.xml + 条目数 |
| `program.paste_st` | program | L1–L3 | 把 ST 代码粘进编辑器并转换 |
| `build.convert_all` | build | L1–L3 | 全部转换：从 Progress.txt 读错误数 |
| `build.program_check` | build | L2–L3 | 程序检查：读「无错误」判定文本 |
| `build.error_detail` | build | L2–L3 | 故意写错：定位错在哪个编译阶段 |
| `batch.projects` | build | L3 | 同会话批量出 3 个工程（各自 0 错） |
| `project.reopen` | project | L4 | 存盘→重开→步数仍在（L4） |

## 未打通

| 项 | 卡在哪 |
|---|---|
| `build.error_line` | 行级错误定位：转换结果面板无可读文本，Progress.txt 只到阶段级 |
| `project.check` | 工程校验是两工程比对，不是校验本工程 |
| `label.import_xml` | XML 导入能进全局标签，但样例结构体有 1 个 Error |
| `program.read_st` | .gx3 里 _Project.txc 是二进制，程序体在 .w3pa |
| `online.write` | 需要真实 PLC；用户口径只做离线 |
| `ladder.write` | 梯形图编辑器是自绘控件，无法程序化写网络 |
