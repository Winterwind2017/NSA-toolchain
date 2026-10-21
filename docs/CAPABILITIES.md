# 能力清单（自动生成）

> 由 `python tools/gen_readme_counts.py` 从 `docs/registry.yaml` + `src/acadkit/caps.py` 生成，**不要手改**。

`caps` 里每条能力都能真机跑一遍（动作 + 判据 + 环境自检），级别含义见 [`JUDGE_SPEC.md`](JUDGE_SPEC.md)。

## 总览

registry 64 条 = verified 56 + usable_unjudged 0 + pending 0 + dead 8 + external 0；内核实现 58 条，覆盖 56 个 registry id。

## 按族

- `ae`（1）：`ae.db`
- `block`（3）：`block.define`、`block.insert_with_attributes`、`block.short_attributes`
- `boolean`（4）：`boolean.union`、`boolean.subtract`、`boolean.intersect`、`boolean.section_slice`
- `dim`（12）：`dim.linear`、`dim.aligned`、`dim.diametric`、`dim.radial`、`dim.angular`、`dim.ordinate`、`dim.arc`、`dim.baseline`、`dim.continuous`、`dim.tolerance`、`dim.fit_code`、`dim.api_missing`
- `env`（2）：`env.sysvar`、`env.dimstyle`
- `export`（4）：`export.dwg`、`export.dxf`、`export.pdf`、`export.pdf_multipage`
- `frame`（2）：`frame.titleblock`、`layout.multipage`
- `gdt`（1）：`gdt.tolerance`
- `geom`（8）：`geom.line`、`geom.circle`、`geom.arc`、`geom.polyline`、`geom.rect`、`geom.ellipse`、`geom.spline`、`geom.hatch`
- `layer`（3）：`layer.create`、`layer.set_current`、`layer.snapshot`
- `lisp`（1）：`lisp.execute`
- `pid`（1）：`pid.symbol`
- `plc`（1）：`plc.build`
- `solid`（2）：`solid.primitive`、`solid.extrude`
- `symbol`（5）：`symbol.roughness`、`symbol.weld`、`symbol.centerline`、`symbol.centermark`、`symbol.balloon`
- `table`（3）：`table.bom`、`table.grid`、`table.chinese`
- `text`（3）：`text.single`、`text.mtext`、`text.style`
- `view`（2）：`view.zoom`、`projection.orthographic`

## 明细

| 能力 | 族 | 级别 | registry 状态 | 说明 |
|---|---|---|---|---|
| `ae.db` | ae | L0–L2 | verified | Electrical 元件库：只读打开 + 数表数行 + 哈希不变 |
| `block.define` | block | L1–L4 | verified | 块定义 + 属性定义 |
| `block.insert_with_attributes` | block | L1–L4 | verified | 块插入 + 属性值 |
| `block.short_attributes` | block | 负例 | （负例，不在 registry） | 负例：属性少一个 → 判据必须失败 |
| `boolean.intersect` | boolean | L1–L4 | verified | 交集：2→1，V=2000 |
| `boolean.section_slice` | boolean | L3–L4 | verified | SLICE：两块体积之和=原体积 |
| `boolean.subtract` | boolean | L1–L4 | verified | 差集：2→1，V=6000 |
| `boolean.union` | boolean | L1–L4 | verified | 并集：2→1，V=10000 |
| `dim.aligned` | dim | L1–L4 | verified | 对齐标注：Measurement |
| `dim.angular` | dim | L1–L4 | verified | 角度标注：Measurement=π/2 |
| `dim.api_missing` | dim | 负例 | （负例，不在 registry） | 负例：AddDimLinear 不存在（必须抛错） |
| `dim.arc` | dim | L1–L4 | verified | 弧长标注：Measurement=R·θ |
| `dim.baseline` | dim | L1–L4 | verified | 基线标注：两条同基 Measurement |
| `dim.continuous` | dim | L1–L4 | verified | 连续标注：两段首尾相接且和=总长 |
| `dim.diametric` | dim | L1–L4 | verified | 直径标注：Measurement=2R |
| `dim.fit_code` | dim | L3 | verified | 配合代号查表（纯 Python） |
| `dim.linear` | dim | L1–L4 | verified | 线性标注：Measurement/文字外侧 |
| `dim.ordinate` | dim | L1–L4 | verified | 坐标标注：Measurement=X |
| `dim.radial` | dim | L1–L4 | verified | 半径标注：Measurement=R |
| `dim.tolerance` | dim | L2–L4 | verified | 尺寸公差：DIMTOL+TextOverride 读回 |
| `env.dimstyle` | env | L2 | verified | 标注样式：ActiveDimStyle + DIMTXT |
| `env.sysvar` | env | L2 | verified | 系统变量：设置/读回/还原 |
| `export.dwg` | export | L0–L4 | verified | DWG：文件 + AC10 + 重开一致 |
| `export.dxf` | export | L0–L4 | verified | DXF：段 + 族计数 + 重新导入 |
| `export.pdf` | export | L0–L3 | verified | PDF：A3 + 非空白 |
| `export.pdf_multipage` | export | L0–L3 | verified | 多页 PDF：逐布局出图 + 合并（每页 A3 且有墨） |
| `frame.titleblock` | frame | L3–L4 | verified | A3 图框 + 标题栏 6 属性 |
| `layout.multipage` | frame | L2–L4 | verified | 新建布局 + 视口 |
| `gdt.tolerance` | gdt | L1–L4 | verified | 形位公差：ACDBFCF + 符号码 |
| `geom.arc` | geom | L1–L4 | verified | 圆弧：Center/Radius/起止角 |
| `geom.circle` | geom | L1–L4 | verified | 圆：计数/半径/面积=πR²/重开 |
| `geom.ellipse` | geom | L1–L4 | verified | 椭圆：长短轴/面积 |
| `geom.hatch` | geom | L1–L4 | verified | 填充：ANSI31/面积 |
| `geom.line` | geom | L1–L4 | verified | 直线：计数/端点/长度/重开 |
| `geom.polyline` | geom | L1–L4 | verified | 多段线：顶点/闭合/长度 |
| `geom.rect` | geom | L1–L4 | verified | 矩形：闭合/4 顶点/面积 |
| `geom.spline` | geom | L1–L4 | verified | 样条：控制点数 |
| `layer.create` | layer | L2–L4 | verified | 建图层：Name/Color 读回 |
| `layer.set_current` | layer | L2–L4 | verified | 设当前层 + 新实体落层 |
| `layer.snapshot` | layer | L3–L4 | verified | 图层状态快照：属性级保存→改→恢复 |
| `lisp.execute` | lisp | L1–L4 | verified | 命令行执行 LISP（不加载文件） |
| `pid.symbol` | pid | L1–L4 | verified | P&ID 符号：闸阀/泵/仪表气泡（程序化画） |
| `plc.build` | plc | L1–L4 | verified | PLC 模块图：规格取自 ace_plc.mdb + 程序化绘制 |
| `solid.extrude` | solid | L1–L4 | verified | 拉伸：体积 = 轮廓面积 × 高度 |
| `solid.primitive` | solid | L1–L4 | verified | 基本体：box/cylinder/sphere 体积 |
| `symbol.balloon` | symbol | L1–L4 | verified | 序号气泡：MULTILEADER + 序号 |
| `symbol.centerline` | symbol | L1–L4 | verified | 中心线：线型 + 两端超出 |
| `symbol.centermark` | symbol | L1–L4 | verified | 中心标记：十字过圆心 |
| `symbol.roughness` | symbol | L1–L4 | verified | 粗糙度符号：3 线 + Ra 文字 |
| `symbol.weld` | symbol | L1–L4 | verified | 焊接符号：2 线 + 焊缝尺寸 |
| `table.bom` | table | L1–L4 | verified | BOM 表：逐格 + 合计 |
| `table.chinese` | table | L1–L4 | verified | 中文表格：CN 样式 + 重开不丢字 |
| `table.grid` | table | L1–L4 | verified | 通用网格表：逐格 + 合计 |
| `text.mtext` | text | L1–L4 | verified | 多行文字：内容/宽度 |
| `text.single` | text | L1–L4 | verified | 单行文字：内容/位置/字高 |
| `text.style` | text | L2–L4 | verified | 文字样式：新增 + 字体读回 |
| `projection.orthographic` | view | L1–L4 | verified | 三视图投影：CSG→front/top/left（可见/隐藏/轴线分层） |
| `view.zoom` | view | L3 | verified | ZoomExtents：视图包住几何 |

## 未实现的能力

见 [`UNSUPPORTED.md`](UNSUPPORTED.md)（dead 与 external 两张表）。
