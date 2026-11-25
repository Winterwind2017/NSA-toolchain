# 设计层

打开 CAD 之前的计算和查法。不连接 SolidWorks、AutoCAD 或 PLC。

```
design/
  design_calc/     纯 Python 选型计算，无第三方依赖
  knowledge/       知识库，入口是 knowledge/_index.md
  tests/           核心公式的离线测试
```

技能 `skills/ww-nsa-design` 规定七段流程：需求、方案、选型、详细设计、装配、出图、交付。算完再把建模交给 `ww-solidworks-automation` 或 `ww-nx-automation`。

## 调用

仓库根目录：

```bash
# Windows PowerShell
$env:PYTHONPATH = "design"
python -m pytest design/tests -q
```

```bash
# bash
PYTHONPATH=design python -c "from design_calc import motor, cylinder, cycle_time"
```

核心入口：`motor`、`cylinder`、`ballscrew`、`linear_guide`、`reducer`、`pneumatic`、`cycle_time`、`tolerance`、`strength`、`gear`、`transmission`。其余模块是扩展计算（液压、真空、弹簧、成本等），函数签名以各文件 docstring 为准。

## 判据

一次选型要能复核三个数里的相关项：气缸缸径来自 `F / (负载率 × 压力)` 再向上圆整；伺服负载惯量是 `m (lead / 2π)²`；节拍先把同一 `group` 取最大值，再把组串联。`warnings` 必须逐条处理，或者写明为什么接受。

公式来自 Shigley、GB 和 THK / HIWIN / SMC 选型手册的常用式，是方案计算，不是替代厂家样本的最终校核。
