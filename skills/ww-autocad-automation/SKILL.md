---
name: ww-autocad-automation
description: >
  用 acadkit 在本机 AutoCAD 2025 上做二维绘图/标注/表格/块/图框/三维实体/布尔/出图自动化，
  并**用几何判据验证结果**。当用户要求画线/圆/弧/多段线/样条/填充，加线性/对齐/角度/
  坐标/弧长/基线/连续/公差标注，建文字/表格/块与属性/图框标题栏/布局视口，建 3D 实体与
  布尔/剖切，做三视图投影，导出 DWG/DXF/PDF（含多页），读 Electrical 元件库或画 PLC 图，
  或问"某个 AutoCAD 命令/COM 方法能不能用、为什么没效果"时使用。
  内含实测通过的配方、必须检查的判据、已证伪不可用的能力清单，以及环境护栏。
  Use for AutoCAD automation, geometry-verified CAD edits, drawing/annotation/table/block
  pipelines, DXF/PDF export, and diagnosing silent no-op ActiveX calls.
---

# ww-autocad-automation

> **这是独立技能仓库**，不随执行内核一起分发。
> 执行内核是 [acadkit](https://github.com/Winterwind2017/autocad-agent-kit)（Python 库 + CLI + MCP），
> 本仓库只负责"**怎么用 + 怎么验证 + 什么别试**"。
> 能力清单以 `capabilities.json` 快照为准（出处：内核 commit + acadkit 版本）。

## 这个技能解决什么

AutoCAD 的 ActiveX/命令行接口有一批**反直觉**的地方：`PlotToFile` 返回 True 但文件
0 字节、`Solid3D.Boolean` 并集把 12000 算成 4000、`MLeader.TextString` 赋值成功读回
空串、`AddBox` 的原点是**中心**不是角点、`-LAYERSTATE` 动过图层表就永久挂起。
结果就是：**调用不报错、几何/文件却不对**（本技能称为"假成功"）。

这个技能把这些坑固化成了三样东西：**配方**（怎么调）、**判据**（怎么证明成功）、
**证伪清单**（哪些根本别试）。

## 开工前 30 秒

1. `acadkit status` —— 确认环境：AutoCAD 是否在跑、`CPROFILE` 是否 `<<VANILLA>>`、
   文档数、`.sv$`、版本。**只附加、不启动**。
2. `acadkit list` —— **只用这张表**里的能力（每条都有动作 + 判据 + 真机通过）。
   表里没有的，先 `acadkit registry` 看状态：`dead` 的别再试，
   `usable_unjudged`/`pending` 的可以试，但必须自己补判据。
3. `acadkit registry --status dead` —— 明确"别试"的边界。
4. 动手前先想清楚判据：这次改动应该让**实体数 / 面积 / 长度 / 体积 / 属性 /
   文件签名**中的哪一个变化？说不出来就先别调。

没装内核时先装（Windows + AutoCAD 2025 完整版）：

```bash
pip install -e <acadkit 仓库>
acadkit selftest        # 离线自检：registry / caps / 判据
acadkit-mcp             # 需要 MCP 时（stdio）
```

## 铁律（违反必踩坑）

| 铁律 | 原因 / 证据 |
|---|---|
| **判据从 AutoCAD 读回，不看返回值** | `PlotToFile` 返回 True、文件 0 字节；`Boolean` 返回 None 却算错体积；`MLeader.TextString` 赋值成功读回空串 |
| **`AddBox` 的 origin 是中心** | 40 宽盒子放 x=500 与 x=520：角点模型并集 12000，中心模型 10000 —— 实测 10000 |
| **布尔走命令行** `_.UNION/SUBTRACT/INTERSECT` | ActiveX `Boolean(1,·)` 算错、`Boolean(3,·)` 报"参数 Operation 无效"；SUBTRACT 要两组选择集 `h1 "" h2 ""`，**句柄必须在执行前取**（合并后实体被删） |
| **出图前 `BACKGROUNDPLOT=0`，用完还原并读回** | 默认 2（后台出图）时 `PlotToFile` 立刻返回、文件要等文档关闭才落盘 |
| **命令行用 `(vl-cmdf …)` 不用 `(command …)`** | 双文档（基线 + 用例）下 `(command …)` 偶发挂起；`-LAYERSTATE` 只要动过图层表就**永久挂起**（改用 `layer.snapshot`） |
| **表格第 0 行是合并标题行** | 往 (0,1..) `SetText`：内存读得到、落盘重开变空串（ASCII 也一样）；表头放第 1 行 |
| **中文单元格要挂 TrueType 样式** | `SetCellTextStyle(r,c,"CN")` + SimSun，否则默认 `Standard`(txt.shx) 落盘丢字 |
| **`LWPOLYLINE` 没有 `NumberOfVertices`** | 只有旧 `POLYLINE` 有；顶点读 `Coordinates` 的坐标对 |
| **标注非关联 + `TextPosition` 会自动避让** | ActiveX 建的标注不跟随几何；传 (30,10) 读回 (30,11.875)，只判"文字在哪一侧" |
| **多布局出图不会产多页** | `Plot.SetLayoutsToPlot` + `PlotToFile` 不落盘，`StartBatchMode` 直接 E_FAIL；多页 = 逐布局出图 + 合并 |
| **`CPROFILE` 是文档级变量** | 没开文档读不到（返回 None）；直接启动 `acad.exe` 会落到 `<<ACADE>>`，必须 `/p "<<VANILLA>>"` |
| **别为 `(load …)` 改 `TRUSTEDPATHS`/`SECURELOAD`** | 持久化变量，忘还原就污染用户配置；要跑 LISP 用内联 `(progn …)` |
| **收尾用 `clean_quit`，不要 `Stop-Process -Force`** | 强杀会留 `%TEMP%\*.sv$`，下次启动弹"图形修复" |
| **`AddText` 参数顺序是（文字, 点, 字高）**；`AddDimRotated` 要 4 个参数（含旋转角） | 顺序错报"类型不匹配"；少参数报"无效的参数数目" |
| **生成了 COM 类型库包装就删 `%TEMP%\gen_py`** | `EnsureModule` 缓存会让 `GetActiveObject` 返回早期绑定对象，属性名按类型库大小写（`fontFile` ≠ `FontFile`） |

## 怎么执行

CLI 与 MCP 暴露的是同一批能力；脚本里用 CLI 更省上下文，Agent 里用 MCP 更直接。

```bash
acadkit status                              # 环境（只附加）
acadkit list --family geom                  # 能用什么
acadkit cap geom.circle --param radius=50   # 跑一条：动作 + 判据 + 环境自检
acadkit run --only geom,dim                 # 跑一组（每条都存盘重开验一遍）
acadkit judges                              # 判据清单与出处
```

`acadkit cap` 返回的是**判据结果**：`ok` 由 `all(checks)` 算出，`checks` 里有
L1 计数、L2 属性、L3 几何、L4 重开与环境自检；任何一项读不到就失败，不会猜。

## 能力索引

<!-- gen:capabilities:BEGIN -->
本表由 `tools/sync_capabilities.py` 从 acadkit 生成的 `capabilities.json` 渲染，**不要手改**（`tests/test_skill.py` 会校验）。

共 **56** 条 verified 能力（内核 `acadkit 0.1.0`，commit `0810d40`）。完整状态：`acadkit registry`；单条跑：`acadkit cap <id>`。

| 能力族 | 能力（级别） |
|---|---|
| **标注**（11） | `dim.aligned`（L1–L4） `dim.angular`（L1–L4） `dim.arc`（L1–L4） `dim.baseline`（L1–L4） `dim.continuous`（L1–L4） `dim.diametric`（L1–L4） `dim.fit_code`（L3） `dim.linear`（L1–L4） `dim.ordinate`（L1–L4） `dim.radial`（L1–L4） `dim.tolerance`（L2–L4） |
| **几何**（8） | `geom.arc`（L1–L4） `geom.circle`（L1–L4） `geom.ellipse`（L1–L4） `geom.hatch`（L1–L4） `geom.line`（L1–L4） `geom.polyline`（L1–L4） `geom.rect`（L1–L4） `geom.spline`（L1–L4） |
| **符号**（5） | `symbol.balloon`（L1–L4） `symbol.centerline`（L1–L4） `symbol.centermark`（L1–L4） `symbol.roughness`（L1–L4） `symbol.weld`（L1–L4） |
| **布尔/剖切**（4） | `boolean.intersect`（L1–L4） `boolean.section_slice`（L3–L4） `boolean.subtract`（L1–L4） `boolean.union`（L1–L4） |
| **导出**（4） | `export.dwg`（L0–L4） `export.dxf`（L0–L4） `export.pdf`（L0–L3） `export.pdf_multipage`（L0–L3） |
| **图层**（3） | `layer.create`（L2–L4） `layer.set_current`（L2–L4） `layer.snapshot`（L3–L4） |
| **表格**（3） | `table.bom`（L1–L4） `table.chinese`（L1–L4） `table.grid`（L1–L4） |
| **文字**（3） | `text.mtext`（L1–L4） `text.single`（L1–L4） `text.style`（L2–L4） |
| **块**（2） | `block.define`（L1–L4） `block.insert_with_attributes`（L1–L4） |
| **系统变量/样式**（2） | `env.dimstyle`（L2） `env.sysvar`（L2） |
| **图框/布局**（2） | `frame.titleblock`（L3–L4） `layout.multipage`（L2–L4） |
| **实体**（2） | `solid.extrude`（L1–L4） `solid.primitive`（L1–L4） |
| **电气数据**（1） | `ae.db`（L0–L2） |
| **形位公差**（1） | `gdt.tolerance`（L1–L4） |
| **LISP**（1） | `lisp.execute`（L1–L4） |
| **P&ID**（1） | `pid.symbol`（L1–L4） |
| **PLC**（1） | `plc.build`（L1–L4） |
| **投影**（1） | `projection.orthographic`（L1–L4） |
| **视图**（1） | `view.zoom`（L3） |
<!-- gen:capabilities:END -->

## 别试这些（已证伪或不可达，做了也是白做）

<!-- allow:non-verified:BEGIN -->
| 能力 | 状态 | 实测结论 |
|---|---|---|
| `dim.associative` | 判死 | ActiveX 标注天然非关联；`DIMLINEAR` 点选/选对象/预选、`DIMREASSOCIATE`、`OSMODE`+`REGEN` 六种输入都卡提示符或 `Measurement` 不跟随。替代=NETLOAD .NET 插件用 `DimensionAssociation`（进程内），或保持非关联 + 显式重建 |
| `layer.state` | 判死 | `-LAYERSTATE` 动过图层表后 Save 永久卡在命令提示符（`SendCommand`/`command`/`vl-cmdf` 全试过）。替代=`layer.snapshot`（属性级快照→改→恢复） |
| `solid.revolve` | 判死 | `AddRevolvedSolid` 对 XY 矩形/圆/3D 多段线三种轮廓都报"输入无效"，命令行 `_.REVOLVE` 也不生成实体。替代=拉伸 + 布尔逼近 |
| `view.projection_builtin` | 判死 | `SOLVIEW/SOLDRAW/SOLPROF/VIEWBASE/SECTION/FLATSHOT/-FLATSHOT/EXPORTLAYOUT` 实测全不存在。替代=`projection.orthographic`（自建 CSG 投影） |
| `constraint.geometric` | 判死 | 完整版也没有 `GEOMCONSTRAINT/DIMCONSTRAINT/PARAMETERS`；.NET 独立建约束组能建但不求解。替代=Python 侧参数驱动重建 |
| `dim.update` | 判死 | `DIMUPDATE` 命令不存在。替代=删除重建，或改标注属性（`TextOverride`/`Measurement`） |
| `block.edit_inplace` | 判死 | `BEDIT/ATTSYNC/ATTREDEF/BATTMAN` 均不存在。替代=改块定义 + 重插全部引用 |
| `interfere` | 判死 | `INTERFERE` 命令不存在。替代=布尔求交后看结果体积，>0 即干涉 |
<!-- allow:non-verified:END -->

负例（故意失败，用来证明判据有效）：`dim.api_missing`（`AddDimLinear` 不存在，
必须抛错）、`block.short_attributes`（少一个属性，判据必须失败）。

逐条证据与最小复现见内核仓库
[`docs/PITFALLS.md`](https://github.com/Winterwind2017/autocad-agent-kit/blob/main/docs/PITFALLS.md)。

## 典型任务配方

### 一条命令验证一个能力

```bash
acadkit cap geom.arc
acadkit cap dim.linear --param expected=80
acadkit cap table.chinese
```

参数用 `--param k=v` 覆盖默认值；每条的默认参数就是配方的一部分
（`acadkit list` 与 `capabilities.json` 里都能看到级别）。

### 几何 + 标注 + 存盘重开

```bash
acadkit run --only geom,dim
```

判据不是"命令没报错"，而是：实体数 +1、`Radius/Area/Measurement` 读回一致、
存盘重开后按句柄再读一遍仍一致。

### 表格（BOM / 中文）

```bash
acadkit cap table.bom        # 5 行排法：标题/表头/2 明细/合计，合计=明细之和
acadkit cap table.chinese    # CN(SimSun) 样式 + 中文单元格，重开不丢字
```

### 块与属性

```bash
acadkit cap block.define                  # 块定义 + 2 个属性定义
acadkit cap block.insert_with_attributes  # 插入 + 逐个 Tag 读回
acadkit cap block.short_attributes        # 负例：少属性必须失败
```

### 图框 + 布局 + 多页 PDF

```bash
acadkit cap frame.titleblock        # A3 图框面积 + 标题栏属性
acadkit cap layout.multipage        # 布局视口 2→3，重开仍 3
acadkit cap export.pdf_multipage    # 逐布局出图 + 合并；判据逐页 A3 且每页有墨
```

### 三维实体 / 布尔 / 剖切

```bash
acadkit cap solid.primitive   # box 8000 / cylinder 6283.185 / sphere 4188.79
acadkit cap boolean.union     # 并集体积 10000（ActiveX 会算成 4000，别用）
acadkit cap boolean.subtract  # 6000（两组选择集）
acadkit cap boolean.section_slice  # SLICE 后两块体积之和 = 8000
```

### 三视图投影

```bash
acadkit cap projection.orthographic
```

内核按 CSG 模型（`box`/`cyl` + `op=add|sub`）独立重算投影：主视/俯视/左视，
可见/隐藏/轴线分层；判据**不信任 builder**，重新算一遍再比计数。

### Electrical 元件库 / PLC 模块图

```bash
acadkit cap ae.db      # 只读打开 AeData 的元件库，读前后 SHA-256 相同
acadkit cap plc.build  # 规格取自 ace_plc.mdb，图形程序化画（不需要 ACADE 模板）
```

这两条需要本机装过 AutoCAD Electrical（`~/Documents/Acade 2025/AeData`）；
没有时会失败并给出原因，**不要**自己编数据。

### 导出

```bash
acadkit cap export.dwg   # DWG 魔数 AC1032 + 句柄
acadkit cap export.dxf   # DXF 族直方图 + 重装（需要 ezdxf）
acadkit cap export.pdf   # A3 + 非空白（背景出图变量已还原）
```

## 判据四级（这就是这个技能的核心）

| 级别 | 内容 | 例子 |
|---|---|---|
| L1 | 计数：目标表/类型的数量按预期变化 | 圆 +1、视口 2→3 |
| L2 | 属性读回：关键字段与输入一致 | `Radius=25`、`Measurement=60`、`FontFile=SimSun` |
| L3 | 几何自洽：用解析值交叉验证 | `Area≈πR²`、`Volume=12000`、PDF 每页 ops>0 |
| L4 | 存盘重开：DWG 重开后按句柄再读一遍 | 属性仍一致、计数仍一致 |

外加**每例前后各一次环境自检**：`CPROFILE`、`TRUSTEDPATHS/SECURELOAD` 未变、
文档数恢复、无 `.sv$`、进程数、单实例、无模态、出图变量已还原。

## 环境铁律

- 必须 `acad.exe /p "<<VANILLA>>"`；`CPROFILE` 是文档级变量，没文档读不到。
- 用例期间保持一个基线文档；用例在第二个文档里跑。
- 收尾 `clean_quit`（关文档 → Quit → 等进程消失），不要 `Stop-Process`。
- 跑真机套件：`python tests/run_all.py`（离线 + 文档 + 真机），
  单例超时会被看门狗强杀并写 `TIMEOUT.txt`。

## 需要细节时读这些

内核仓库（同一位作者，独立仓库）：

| 文件 | 内容 |
|---|---|
| [`docs/PITFALLS.md`](https://github.com/Winterwind2017/autocad-agent-kit/blob/main/docs/PITFALLS.md) | 逐条踩坑记录（13 类），改代码前扫一遍 |
| [`docs/UNSUPPORTED.md`](https://github.com/Winterwind2017/autocad-agent-kit/blob/main/docs/UNSUPPORTED.md) | dead 清单与替代方案（由 registry 生成） |
| [`docs/RECIPES.md`](https://github.com/Winterwind2017/autocad-agent-kit/blob/main/docs/RECIPES.md) | 加一条能力的标准流程（registry→build→judge→caps→真机→测试） |
| [`docs/JUDGE_SPEC.md`](https://github.com/Winterwind2017/autocad-agent-kit/blob/main/docs/JUDGE_SPEC.md) | 判据四级与环境自检的完整定义 |
| `references/pitfalls.md` | 本技能侧的坑清单（带最小复现与修法） |
| `references/recipes.md` | 更完整的任务配方与判据数字 |
| `references/checklists.md` | 交付前检查清单 |

## 交付前的自检三问

1. **数字变了吗？** 实体数/面积/长度/体积/属性/页数，至少一个有可复现的前后对比。
2. **落盘还存在吗？** 不只是"文件存在"，要比 mtime、大小下限、文件头
   （DWG `AC1032`、DXF `  0\r\nSECTION`、PDF `%PDF-`、PDF 页数）。
3. **负面对照做过吗？** 把关键参数换成已知错误值（少属性、错类型、错层），
   判据必须失败。不能失败的判据，通常也证明不了成功。
