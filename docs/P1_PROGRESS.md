# P1 进度

只记录**已经能跑**的东西，不写计划。每条附验证方式。

## ✅ 步骤 1：包骨架 + `acadkit status` 环境自检

**产出**

```
src/acadkit/
├─ __init__.py          版本
├─ registry.py          载入 docs/registry.yaml（有 PyYAML 用之，无则容错解析）
├─ status.py            环境自检：采集 + 判定 + 渲染
├─ core/com.py          只附加不启动；clean_quit
└─ cli/main.py          status / env-baseline / env-check / registry / selftest
tests/test_offline.py   14 条离线测试（不需要 AutoCAD）
tests/live_env_check.py 真机链路：基线 → 漂移 → 检出 → 还原 → 退出
pyproject.toml          console_script = acadkit
```

**命令**

```bash
acadkit selftest        # 离线自检（registry 60 条 + 校验）
acadkit registry        # 能力清单（--status verified 等）
acadkit status          # 环境自检（只附加，不启动 AutoCAD）
acadkit env-baseline    # 采环境基线 → ~/.acadkit/env_baseline.json
acadkit env-check       # 与基线比对
```

**退出码**：`0` 通过 · `3` AutoCAD 未运行（只读命令的正常结果）· `4` 环境不合规
（profile≠`<<VANILLA>>` 或多实例）· `5` 环境漂移。

## 真机验证记录（2026-10-21）

| 用例 | 期望 | 实测 |
|---|---|---|
| AutoCAD 未运行时 `status` | 只报告、不启动、rc=0 | ✅ 跑完进程数仍为 0 |
| AutoCAD 运行中 `status` | 读到 profile=`<<VANILLA>>`、单实例 OK | ✅ |
| `env-baseline` | 写基线文件 | ✅ `C:\Users\yuche\.acadkit\env_baseline.json` |
| 改 `MEASUREMENT` 1→0 后 `env-check` | 检出 1 项漂移、rc=5 | ✅ `var:MEASUREMENT '1' → '0'` |
| 还原后 `env-check` | 干净、rc=0 | ✅ |
| `clean_quit` | 进程真消失、不留 `.sv$` | ✅ `process_exited=True`，等 1.8 s，`.sv$`=0 |

## 途中修掉的四个真问题（都是跑出来的，不是想出来的）

1. **`dynamic.Dispatch` 会启动 AutoCAD**
   一次 `status` 探测凭空拉起隐藏实例（`Visible=False`，自带 `Drawing1.dwg`）。
   → 改为 `GetActiveObject` 只附加；启动必须显式。
2. **`Documents` 晚绑定下不可枚举**
   `list(app.Documents)` 抛 `TypeError: This object does not support enumeration`。
   → 按索引 `Documents.Item(i)` 取。
3. **未保存文档会让 `Quit()` 弹模态卡死**
   → `save=False` 时先把 `doc.Saved = True`（丢弃修改）。
4. **`Quit()` 是异步的**
   调用返回后进程还活几秒，下一个用例会看到"幽灵实例"。
   → 轮询等进程消失，返回 `process_exited`。

另外把「读不到变量」与「变量为空」分开显示（`（读不到）` vs `（空）`）——
环境漂移判据依赖这个区别。

## ✅ 步骤 2：`judges/` 四族判据 + 每族真机用例 + 每例前后环境自检

**产出**

```
src/acadkit/judges/
├─ base.py        Readback/Drawing/Entity + verdict()（ok 只能由 all(checks) 算出）
├─ read.py        COM 读回：类型白名单、块表、属性、表格单元格、图纸单位
├─ geom.py        circle / line / rect（L1–L4）
├─ dim.py         linear / diametric / radial + "不存在的 API 必须抛错"（负例）
├─ export.py      dwg / dxf / pdf（L0–L4，含"文件是不是这次写的"）
├─ block_table.py block.define / block.insert_with_attributes / table.bom（L1–L4）
├─ pdfinfo.py     最小 PDF 解析（页数 / MediaBox / 解压后的绘图操作符）
├─ dxfinfo.py     DXF 读回（优先 ezdxf，没有则容错 group-code 解析）
├─ envguard.py    环境自检护栏（§3 的七项，前后各一次）
└─ case.py        用例执行器：文档生命周期 + DWG 存盘重开 + DXF 重装 + 合并 checks
src/acadkit/core/launch.py   显式启动（acad.exe /p "<<VANILLA>>"，起错 profile 就退出）
src/acadkit/core/plot.py     SaveAs / PlotToFile 的判据友好封装（含 BACKGROUNDPLOT 还原）
tests/live_judges.py         14 条真机用例（四族 + 2 条负面对照）
tests/test_judges.py         36 条离线判据测试（正例 + 每条判据都必须能失败）
```

**命令**

```bash
acadkit judges              # 判据清单（四族 / 级别 / 覆盖的 registry id）
acadkit judges --json
python tests/live_judges.py [--only geom,dim] [--keep]
```

## 真机验证记录（2026-10-21 · 冷启动，14/14 通过）

一次性跑完：`python tests/live_judges.py`（AutoCAD 未运行时自己用
`/p "<<VANILLA>>"` 起，跑完 `clean_quit`）。总耗时 41.4 s（用例本身）+ 启动 6.0 s。

| 族 | 用例 | 级别 | 实测要点 | 结果 |
|---|---|---|---|---|
| geom | `geom.circle` | L1–L4 | R=25 → Area=1963.4954（πR²）、重开 R/A 不变 | ✅ |
| geom | `geom.line` | L1–L4 | 两端点 (0,0)-(60,0)、Length=60.0 | ✅ |
| geom | `geom.rect` | L1–L4 | 闭合 LWPOLYLINE 4 顶点、Area=1200=40×30 | ✅ |
| dim | `dim.linear` | L1–L4 | `ROTATEDDIMENSION`、Measurement=60.0、文字在尺寸线外侧（读回 y=11.875） | ✅ |
| dim | `dim.diametric` | L1–L4 | `DIAMETRICDIMENSION`、Measurement=50.0=2R | ✅ |
| dim | `dim.radial` | L1–L4 | `RADIALDIMENSION`、Measurement=25.0=R | ✅ |
| dim | `dim.api_missing` | 负例 | `AddDimLinear` → `AttributeError`（"不存在的 API 必须报错"） | ✅ |
| export | `export.dwg` | L0–L4 | 头 `AC1032`、重开后计数 2/2、句柄 2/2 | ✅ |
| export | `export.dxf` | L0–L4 | ezdxf 1.4.3 读回族直方图 = 内存；DXF 重新装回 AutoCAD 计数一致；段含 HEADER/ENTITIES | ✅ |
| export | `export.pdf` | L0–L3 | `%PDF-1.7`、1 页、1191×842 pt（420.2×297.0 mm）、解压后 90 个 `l` + 25 个 `S`；出图 0.25 s | ✅ |
| block-table | `block.define` | L1–L4 | 块内 1 圆 + 2 Attdef（PART_NO/MATERIAL 默认值读回） | ✅ |
| block-table | `block.insert_with_attributes` | L1–L4 | 引用 +1、块名一致、2 个属性逐 Tag 比对、重开后仍是 P-777 / 45# | ✅ |
| block-table | `block.short_attributes` | 负例 | 删掉 1 个属性 → `attr_count` 1≠2、`attr_values` 失败（判据必须失败） | ✅ |
| block-table | `table.bom` | L1–L4 | 5×3：标题行 + 表头 + 2 明细 + 合计；合计 5 = 2+3；重开逐格一致 | ✅ |

**环境自检（每例前后各一次）**：14 例 × 7 项 + PDF 的 `BACKGROUNDPLOT` 还原 1 项
= **99 项全绿** ——
`env_profile`（前后都 `<<VANILLA>>`）、`env_vars`（`TRUSTEDPATHS`/`SECURELOAD`
等无漂移）、`env_documents`（每例 1→1，回不到就判失败）、`env_sv`（0→0）、
`env_process`（1→1）、`env_single_instance`、`env_no_modal`（关文档最慢 1.118 s）、
`env_restored`（出图前改的 `BACKGROUNDPLOT` 已还原并读回核对）。

**跑前/跑后指纹**：

```
跑前：process_count=0, sv_count=0        # 冷启动前 AutoCAD 未运行
启动：acad.exe /p "<<VANILLA>>"，6.0 s 后 COM 可附加
跑后：process_count=0, sv_count=0        # clean_quit process_exited=True（1.3 s）
```

## 途中修掉的八个真问题（都是真机跑出来的）

1. **`AttributeError: Add.ModelSpace` / `<unknown>.Open` 不是"API 不存在"，是代理失效。**
   冷启动第一轮：`geom.circle` 直接挂在 `Add.ModelSpace`；`table.bom` 挂在
   `Open.Close`，还把一个文档残留下来（documents 1→2，`env_documents` 判失败）。
   修法：`Documents.Add/Open` 之后**重新取 `ActiveDocument` 并做一次
   `ModelSpace.Count` 自检**再交给用例；`Close` 失败按文档名重找再试；
   环境快照读到 `documents=-1` / 变量全空时先重新附加再采。
2. **ACDBTABLE 的第 0 行是合并的标题行。**
   往 (0,1)/(0,2) `SetText`，内存读得到，**落盘重开变空串**。先疑心是中文
   编码，后来用纯 ASCII 复现（`NAME`/`QTY` 一样丢），才定位到合并行。
   修法：BOM 改 5 行排法（标题 + 表头 + 明细 + 合计），判据加
   `detail_rows/total_row` 参数。4 行"表头写在第 0 行"的排法在真机上过不了 L4。
3. **PDF 出图默认 `BACKGROUNDPLOT=2`。** `PlotToFile` 立刻返回 True，文件要等
   文档关闭才落盘（探针里轮询 15 s 仍是 0 字节）。置 0 后 0.24–0.27 s 落盘。
   用完还原并**读回校验**（`export.pdf` 的 `env_restored` 检查就是这条）。
4. **DXF 最小解析器必须容错空值行。** MTEXT 的 group 1 为空时 AutoCAD 写空行，
   严格的"每两行一对"会错位（实测 `probe.dxf` 到 2656 行把 `1.0` 当 code），
   结果漏掉 ENTITIES 段。改成"解析不出整数就跳过、自动重新对齐"。
5. **`LWPOLYLINE` 没有 `NumberOfVertices`**（只有旧 `POLYLINE` 有）——
   矩形判据用 `Coordinates` 的顶点对，不读这个属性。
6. **标注文字位置会被自动偏移**：传 (30,10)，读回 (30,11.875)。所以
   "文字在预期侧"只能判方向，不能判相等。
7. **`com_error: 被呼叫方拒绝接收呼叫`（RPC_E_CALL_REJECTED）在"读"的路上也会出现。**
   冷启动那一轮，`build_missing_api` 里 `doc.ModelSpace` 被拒收，用例直接报错。
   修法：`core.com.retry()` 已有忙等待；这次把它铺到**读回路径**
   （`ModelSpace`/`Count`/`Blocks`/`GetVariable`）和用例里每一次取 `ModelSpace`
   上——忙 ≠ 没有这个属性，也 ≠ 能力失败。
8. **退出前 `app.Documents` 自己也会失效。** 最后一轮 `clean_quit` 读
   `Documents.Count` 报 `AttributeError: AutoCAD.Application.Documents`，
   于是 "以为退出了、其实进程还在"（那轮 exit=1 就是它）。修法：退出前
   `com.refresh(app)` 重取代理，失效就再取；同时 `refresh()` **只换真实 COM
   对象**——离线测试用假对象，绝不能因此连上并 Quit 掉用户开着的 AutoCAD。

## 已知限制（写进判据之前的边界）

* 标注是**非关联**的：COM `AddDimRotated` 不建立与线的关联，改几何不会自动更新
  `Measurement`，所以 `DIMASSOC=2` 的联动这一条**没测**。
* 表格单元格的文字样式：默认 `Standard`（txt.shx）下中文即便在非标题行也可能
  丢字；本步只测了 ASCII 内容 + 5 行排法。
* `dim.fit_code`（GB/T 1800 表值对照）还没有判据，等 `fit_deviation` 移植后再落。
* `export.pdf` 只覆盖"模型空间 + 单页 A3"；多布局/多页（`export.pdf_multipage`
  已登记为 dead）没测。

## 下一步（P1 剩余）

| 步 | 内容 | 估时 |
|---|---|---|
| 3 | `verified` 30 条里的前 12 条落成 CLI 子命令（判据已在，CLI 面还没铺开） | 1 天 |
| 5 | 22 条 `usable_unjudged` 补到 L2 | 1.5 天 |
| 6 | 标注关联（DIMASSOC=2 联动）、中文表格样式、`fit_code` 判据 | 0.5 天 |
