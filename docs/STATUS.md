# gxkit 现状

引擎 **GX Works3 1.117.0.1**，内核 **gxkit 0.2.0**。目标机型 **FX5U**，程序语言 **ST**，范围 **离线**。

## 数字

- 真机通过能力：**9** 条
- 一条能力一个干净会话（启动约 10 s）；`batch.projects` 是唯一在同会话内连做的能力
- 未打通：见 `UNSUPPORTED.md`

## 能力

| id | family | level | 做什么 | 判据来源 |
|---|---|---|---|---|
| `project.new` | project | L1 | 新建 FX5U+ST 工程 | 标题含 `[PRG] [ST]` |
| `project.save` | project | L1–L2 | 另存为 `.gx3`（含读回） | 文件存在 + `!!Config.xml` 的 `Unit` |
| `project.meta` | inspect | L1–L2 | 解包读 Config/条目数 | ZIP 条目 + Config |
| `program.paste_st` | program | L1–L3 | ST 代码粘进编辑器 | 标题 `N步` + 编译错误数 |
| `build.convert_all` | build | L1–L3 | 全部转换 | `Progress.txt` 的 `错误：0、警告：0` |
| `build.program_check` | build | L2–L3 | 程序检查（指令/双线圈/软元件） | 对话框 UIA 文本 `程序检查已完成。无错误。` |
| `build.error_detail` | build | L2–L3 | 故意写错 → 定位错在哪个编译阶段 | `Progress.txt` 的 `failed_stages` |
| `batch.projects` | build | L3 | 同会话连出 3 个工程（变体长度不同） | 3 个文件都存在 + 各自 0 错 + 3 个不同大小 |
| `project.reopen` | project | L4 | 存盘→关→重开→步数仍在 | 标题文件名 + `N步` |

## 三个判据层

1. **文件层**：`.gx3` 存在、大小、`!!Config.xml` 的机型。
2. **编译层**：`ConvertData/Progress.txt` 的逐阶段 `Error/Warning`，以及 `failed_stages`。
3. **软件层**：`工具 → 程序检查` 执行后的判定文本（UIA 可读）。

## 复现

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'
python -m gxkit selftest
python -m gxkit run --workdir D:\tmp\run1     # 9/9，约 13 分钟
```
