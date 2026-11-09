# 任务配方（含判据数字）

> 默认参数下的期望值；换参数要同步换期望。

## 建块 / 圆柱

```bash
nxkit cap block.create      # 100×50×20 → 体积 100000，面积 16000，面 6，边 12
nxkit cap cylinder.create   # Ø40×30 → 37699.11，面 3
nxkit cap block.two_bodies  # 100000 + 8000 = 108000，实体 2
```

## 布尔

```bash
nxkit cap boolean.subtract  # A(100×50×20) − B(20×20×20 在 A 内) → 92000
nxkit cap boolean.union     # 100000（B 完全在 A 内）
nxkit cap boolean.intersect # 8000
```

判据：实体数 1、体积、重开后仍是 1 个实体。

## 曲线

```bash
nxkit cap curve.line   # (0,0,0)-(100,0,0) → 长度 100
nxkit cap curve.arc    # R25 整圆 → 周长 157.0796
```

## 拉伸

```bash
nxkit cap extrude.rect  # 100×50 截面拉 10 → 50000，面 6
nxkit cap extrude.ring  # 外框 100×50，内框 40×20 → 42000，面 10
```

## 装配

```bash
nxkit cap asm.add_component    # RootComponent 子节点 1
nxkit cap asm.two_components   # 2 个组件，存盘
```

组件路径要先有 `.prt`：动作内部会先建基准零件并 `SaveAs`。

## 制图

```bash
nxkit cap drawing.sheet      # A3：420×297
nxkit cap drawing.base_view  # Front 视图，名字 Front@1
```

## 导出

```bash
nxkit cap export.step  # 文件头 ISO-10303-21
nxkit cap export.iges  # .igs 落盘
```

## 属性 / 测量 / 拓扑

```bash
nxkit cap attr.string   # 写 NXKIT_STR=hello-nx，重开仍在
nxkit cap attr.int      # 写整数属性
nxkit cap measure.mass  # 体积 100000 / 面积 16000 / 重心
nxkit cap body.topo     # 面 6 / 边 12
```

## 一次跑全部

```bash
nxkit run                     # 一次 NX 会话（约 15 s）
nxkit run --only solid,boolean
```
