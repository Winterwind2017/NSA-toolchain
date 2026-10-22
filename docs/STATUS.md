# gxkit 现状

引擎 **GX Works3 1.117.0.1**，内核 **gxkit 0.1.0**。目标机型 **FX5U**，程序语言 **ST**，范围 **离线**。

## 数字

- 真机通过能力：**6** 条（连跑 2 次全绿：439.8 s / 427.1 s）
- 一条能力一个干净会话（启动约 10 s）
- 未打通：见 `UNSUPPORTED.md`

## 能力

| id | family | level | 做什么 | 判据来源 |
|---|---|---|---|---|
| `project.new` | project | L1 | 新建 FX5U+ST 工程 | 标题含 `[PRG] [ST]` |
| `project.save` | project | L1–L2 | 另存为 `.gx3`（含读回） | 文件存在 + `!!Config.xml` 的 `Unit` |
| `project.meta` | inspect | L1–L2 | 解包读 Config/条目数 | ZIP 条目 + Config |
| `program.paste_st` | program | L1–L3 | ST 代码粘进编辑器 | 标题 `N步` + 编译错误数 |
| `build.convert_all` | build | L1–L3 | 全部转换 | `Progress.txt` 的 `错误：0、警告：0` |
| `project.reopen` | project | L4 | 存盘→关→重开→步数仍在 | 标题文件名 + `N步` |

## 复现

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest
python -m gxkit run --workdir D:\tmp\run1     # 6/6，约 7–8 分钟
```
