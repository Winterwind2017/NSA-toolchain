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

`drive_audit.audit_linear_drive` 复核已经选定的丝杠或皮带电机：峰值、RMS、转速、惯量比、斜轴抱闸，丝杠还给了直径和长度就核临界转速。`gear.involute_xy` 只给标准直齿渐开线坐标。`delivery_gate.accept_new_file` 拒绝本轮开始之前就存在的 PDF / STEP。

在本机 SolidWorks 2025（版本号 33.4.1）上：焊件特征 `InsertWeldmentFeature` 和 SolidWorks 窗口连续抓帧已经读回通过。筋特征接口能调用，但这台机器上返回 0，体积不变，所以仍是 `unverified`。形位公差框的读写函数已接上，投影公差带不在这份类型库里，请求它会失败。结构构件的轮廓不复制进仓库。`weldment_library.default_profile()` 会找本机已安装的库，这台机器上是 ISO 方管，配置有 `20 x 20 x 2`、`30 x 30 x 2.6`、`40 x 40 x 4`、`80 x 80 x 5`。切割清单没有特征就返回空列表。
