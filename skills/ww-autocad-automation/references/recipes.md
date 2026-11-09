# 任务配方（含判据数字）

> 所有命令都能直接跑：`acadkit cap <id> [--param k=v]`。
> 判据数字是**默认参数**下的期望值；换参数就要同步换期望。

## 1. 单条能力：动作 + 判据 + 环境自检

```bash
acadkit cap geom.circle                       # 默认 radius=25
acadkit cap geom.circle --param radius=50     # 判据跟着变：Area≈π·50²
```

一次 `cap` 做四件事：建图 → 读回 → 存盘重开 → 判据；前后各一次环境自检。

## 2. 几何

| 能力 | 判据要点 |
|---|---|
| `geom.line` | 计数 +1；两端点坐标；`Length` |
| `geom.circle` | `Center`/`Radius`；`Area≈πR²` |
| `geom.arc` | `Center`/`Radius`/起止角 |
| `geom.polyline` | 顶点数（`Coordinates` 对数，**不是** `NumberOfVertices`）、闭合 |
| `geom.rect` | 闭合多段线、4 顶点、对角点 |
| `geom.ellipse` | 长短轴 + `Area` |
| `geom.spline` | 控制点数 |
| `geom.hatch` | `PatternName`（字符串也要比）、面积≈外环面积 |

## 3. 文字 / 标注

```bash
acadkit cap text.single
acadkit cap text.mtext
acadkit cap text.style
acadkit cap dim.linear --param expected=60
acadkit cap dim.aligned
acadkit cap dim.diametric
acadkit cap dim.radial
acadkit cap dim.angular
acadkit cap dim.ordinate
acadkit cap dim.arc
acadkit cap dim.baseline
acadkit cap dim.continuous
acadkit cap dim.tolerance
acadkit cap dim.fit_code          # 纯 Python 查表：H7@50=+0.025/0
```

## 4. 符号 / 形位公差

```bash
acadkit cap gdt.tolerance     # {\Fgdt;n} 符号码读回
acadkit cap symbol.roughness  # 线 + 文字计数
acadkit cap symbol.weld
acadkit cap symbol.centerline # 线型 + 两端超出
acadkit cap symbol.centermark # 十字过圆心
acadkit cap symbol.balloon    # 圆 + 引线 + 序号
```

## 5. 表格

```bash
acadkit cap table.bom       # 5 行：标题/表头/2 明细/合计；合计 = 明细之和
acadkit cap table.grid
acadkit cap table.chinese   # CN(SimSun) 样式；中文落盘重开完好
```

## 6. 块 / 图框 / 布局

```bash
acadkit cap block.define
acadkit cap block.insert_with_attributes
acadkit cap frame.titleblock      # A3 面积 + 标题栏 6 属性
acadkit cap layout.multipage      # 视口 2→3
```

## 7. 三维 / 布尔 / 剖切

```bash
acadkit cap solid.primitive
acadkit cap solid.extrude          # 40×30×10 → Volume 12000
acadkit cap boolean.union          # 10000
acadkit cap boolean.subtract       # 6000
acadkit cap boolean.intersect      # 2000
acadkit cap boolean.section_slice  # 两块之和 8000
```

布尔三兄弟都走命令行 + 句柄选择；判据是 `3DSOLID.Volume`（ActiveX 布尔会算错）。

## 8. 三视图投影

```bash
acadkit cap projection.orthographic
```

模型默认：100×60×20 底板 + Ø32×10 凸台 + Ø20 通孔。判据：主视 100×30、
俯视 100×60、左视 60×30；可见/隐藏/轴线三段计数与**独立重算**一致。

## 9. 导出

```bash
acadkit cap export.dwg
acadkit cap export.dxf
acadkit cap export.pdf
acadkit cap export.pdf_multipage   # 2 页，每页 A3 且 ops>0
```

## 10. 电气 / PLC（需要本机 AeData）

```bash
acadkit cap ae.db      # 只读打开元件库；读前后 SHA-256 相同
acadkit cap plc.build  # 规格取自 ace_plc.mdb，图形程序化画
```

## 11. 在 Python 里组合多条

```python
import sys; sys.path.insert(0, "<acadkit>/src")
from acadkit import caps, live

cases = [caps.get("geom.rect").case(),
         caps.get("dim.linear").case({"expected": 80.0})]
payload = live.run(cases, workdir="D:/tmp/run1", keep=False)
print(live.summarize(payload))
```

`live.run` 负责起 AutoCAD、逐条跑、收尾 `clean_quit`、汇总；单例超时会强杀并写现场。
