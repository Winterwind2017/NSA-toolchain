# 能力索引（由 tools/sync_capabilities.py 生成，勿手改）

共 **6** 条已验证能力（内核 `gxkit 0.1.0`，commit `5f262ca`，引擎 GX Works3 1.117.0.1，机型 FX5U，语言 ST，仅离线）。

| id | family | level | 说明 |
|---|---|---|---|
| `project.new` | project | L1 | 新建 FX5U + ST 工程 |
| `project.save` | project | L1–L2 | 另存为 .gx3（含读回校验） |
| `project.meta` | inspect | L1–L2 | 解包 .gx3：Config.xml + 条目数 |
| `program.paste_st` | program | L1–L3 | 把 ST 代码粘进编辑器并转换 |
| `build.convert_all` | build | L1–L3 | 全部转换：从 Progress.txt 读错误数 |
| `project.reopen` | project | L4 | 存盘→重开→步数仍在（L4） |

## 未打通

| 项 | 卡在哪 |
|---|---|
| `project.check` | 工程校验结果面板没有稳定读回口 |
| `label.import_xml` | XML 导入能进全局标签，但样例结构体有 1 个 Error |
| `program.read_st` | .gx3 里 _Project.txc 是二进制，程序体在 .w3pa |
| `online.write` | 需要真实 PLC；用户口径只做离线 |
| `ladder.write` | 梯形图编辑器是自绘控件，无法程序化写网络 |
