---
name: ww-nx-automation
description: >
  用 nxkit 在本机 UG NX 2512 上做建模/装配/制图/导出自动化，并**用几何判据验证结果**。
  当用户要求建块/圆柱、布尔（并/差/交）、曲线、拉伸（含内孔截面）、插组件、
  出 A3 图纸与基础视图、写属性、量体积/面积、导出 STEP/IGES，或问
  "NX 某个 API 能不能用、为什么没效果"时使用。内含实测通过的配方、必须检查的
  判据、还没打通的能力清单，以及 NX 特有的坑（Null 哨兵、集合不可遍历、许可证分档）。
  Use for UG NX automation, geometry-verified CAD edits, journal-based NX scripting,
  and diagnosing silent no-op NXOpen calls.
---

# ww-nx-automation

> **这是独立技能仓库**，不随执行内核一起分发。
> 执行内核是 [nxkit](https://github.com/Winterwind2017/nxkit)（Python 库 + CLI），
> 本仓库只负责"**怎么用 + 怎么验证 + 什么别试**"。
> 能力清单以 `capabilities.json` 快照为准（出处：内核 commit + nxkit 版本）。

## 这个技能解决什么

NX 的 NXOpen 接口有一批**反直觉**的地方：builder 的 `Null` 哨兵每种特征都不一样
（`Feature.Null` / `BooleanFeature.Null` / `BaseView.Null`），集合对象没有 `len()`
和下标，布尔之后多个特征指向同一个结果体（直接数会数三遍），拉伸的距离藏在
`Limits.StartExtend.SetValue()` 里，出图/导出的入口不在 `part` 上而在 `session.DexManager`。
结果就是：**脚本不报错、几何/文件却不对**（本技能称为"假成功"）。

这个技能把它们固化成了三样东西：**配方**（怎么调）、**判据**（怎么证明成功）、
**未打通清单**（省得重复踩）。

## 开工前 30 秒

1. `nxkit status` —— 找 `run_journal.exe`、看能力数（**不启动 NX**）。
2. `nxkit selftest` —— 离线自检（动作/判据/负例，不需要 NX）。
3. `nxkit list` —— **只用这张表**里的能力；表里没有的先看
   [`docs/UNSUPPORTED.md`](https://github.com/Winterwind2017/nxkit/blob/main/docs/UNSUPPORTED.md)。
4. 动手前想清楚判据：这次改动应该让**实体数 / 面数 / 边数 / 体积 / 面积 /
   属性 / 文件签名**中的哪一个变化？说不出来就先别调。

没装内核时：

```bash
pip install -e <nxkit 仓库>       # 或 PYTHONPATH=<nxkit>/src
nxkit status
nxkit run --only solid            # 真机跑一族
```

## 铁律（违反必踩坑）

| 铁律 | 原因 / 证据 |
|---|---|
| **判据从 NX 读回，不看返回值** | builder 的 `CommitFeature()` 返回对象也可能几何没变；体积要用 `MeasureManager` 读 |
| **Null 哨兵各不相同** | 块/圆柱/拉伸 `Feature.Null`；布尔 `BooleanFeature.Null`；基础视图 `Drawings.BaseView.Null`。传错直接 `TypeError` |
| **`BodyCollection` 不能 `len()`/下标/`ToArray()`** | 只有 `FindObject`；要实体从 `feature.GetBodies()` 拿 |
| **布尔后按 `Tag` 去重** | `Block(0)`/`Block(1)`/`Subtract(2)` 指向同一结果体，不去重体积会翻三倍 |
| **拉伸距离用 `Limits.StartExtend.SetValue()`** | `StartExtend.Value` 是 `Expression`，直接赋值报只读；`Limits` 实际类型是 `LinearLimits` |
| **截面创建要 5 个参数** | `CreateSectionsUsingCurves(curves, loop, chain_tol, dist_tol, angle_tol)`；带内孔用 `SeparateOuter` |
| **出图枚举叫 `FirstAngle`** | `ProjectionAngleType.First` 不存在；`StandardSheetSize.A3` 存在 |
| **基础视图要给 `SelectedView`** | `CreateBaseViewBuilder(BaseView.Null)` → `SelectModelView.SelectedView = <ModelView>`；`ViewPlacementBuilder.Placement` 只读 |
| **导出走 `session.DexManager`** | `CreateStepCreator()`/`CreateIgesCreator()` → 设 `OutputFile` → `Commit()`；`NXOpen.StepCreator()` 直接构造报 `Invalid self parameter` |
| **`SaveAs` 目标已存在会抛错** | `File already exists`，先删再存 |
| **重开用 `OpenActiveDisplay`** | 返回 tuple，取 `[0]`；`SetWork` 在没显示部件时会失败 |
| **`run_journal` 成功也可能返回退出码 1** | 以 `result.json` 为准，不看退出码 |
| **Python 绑定是子集** | `ufs.Modl` 只有 213 个方法（原生 815），`CreateBlock1` 不在里面；建模走 `NXOpen.Features` |
| **每个 UF 调用都抢许可证** | 反编译 `UF_MODL_create_block1` 见 `JAM_reserve_uf_license("solid_modeling")`；返回码非 0 就是没许可证 |

## 怎么执行

```bash
nxkit status                       # 环境（不启动 NX）
nxkit list                         # 能力清单
nxkit cap block.create             # 一条：建 → 读回 → 存盘重开 → 判据
nxkit run --only boolean           # 一族
nxkit run                          # 全部，一次 NX 会话（约 15 s）
```

`nxkit run` 的判据分四级：L1 计数、L2 属性、L3 几何、L4 存盘重开；
任何一级读不到就失败，不会猜。

## 能力索引

<!-- gen:capabilities:BEGIN -->
本表由 `tools/sync_capabilities.py` 从 nxkit 生成的 `capabilities.json` 渲染，**不要手改**（`tests/test_skill.py` 会校验）。

共 **44** 条 verified 能力（内核 `nxkit 0.1.0`，commit `e918f9f`，引擎 NX 2512）。完整状态：`nxkit list`；单条跑：`nxkit cap <id>`。

| 能力族 | 能力（级别） |
|---|---|
| **特征（拉伸）**（12） | `extrude.rect`（L1–L4） `extrude.ring`（L1–L3） `feature.chamfer`（L1–L3） `feature.chamfer_multi`（L1–L3） `feature.edge_blend`（L1–L3） `feature.hole_array`（L1–L3） `feature.hole_cyl`（L1–L3） `feature.pattern_circular`（L1–L3） `feature.pattern_grid`（L1–L3） `feature.pattern_linear`（L1–L3） `feature.pocket`（L1–L3） `feature.shell`（L1–L3） |
| **实体**（5） | `block.create`（L1–L4） `block.two_bodies`（L1–L4） `cylinder.create`（L1–L4） `solid.cone`（L1–L3） `solid.sphere`（L1–L3） |
| **属性**（4） | `attr.int`（L2） `attr.on_body`（L2） `attr.on_feature`（L2） `attr.string`（L2–L4） |
| **布尔**（4） | `boolean.intersect`（L1–L4） `boolean.subtract`（L1–L4） `boolean.two_tools`（L1–L3） `boolean.union`（L1–L4） |
| **导出**（4） | `export.acis`（L1–L2） `export.iges`（L1–L3） `export.step`（L1–L3） `export.step_ap203`（L1–L2） |
| **曲线**（3） | `curve.arc`（L1–L3） `curve.ellipse`（L1–L3） `curve.line`（L1–L3） |
| **sketch**（3） | `sketch.circle_extrude`（L1–L3） `sketch.extrude`（L1–L3） `sketch.rect`（L1–L2） |
| **装配**（2） | `asm.add_component`（L1–L2） `asm.two_components`（L1–L4） |
| **制图**（2） | `drawing.base_view`（L1–L3） `drawing.sheet`（L1–L2） |
| **测量**（2） | `measure.face_area`（L3） `measure.mass`（L3） |
| **文件**（1） | `file.roundtrip`（L4） |
| **拓扑检查**（1） | `body.topo`（L1–L3） |
| **部件**（1） | `part.new`（L1） |
<!-- gen:capabilities:END -->

## 还没打通（别重复试）

<!-- allow:pending:BEGIN -->
| 能力 | 卡在哪 |
|---|---|
| `feature.hole` | `HolePackageBuilder` 需要点位/面，未打通 |
| `drawing.dimension` | 线性尺寸 builder 的关联能设，`Commit()` 报 `Unable to create a dimension from the selected objects and annotation plane`；`Origin` 只读 |
| `measure.distance` | `MeasureDistance` 没有 `.Distance`，`Information()` 返回 `None` |
| `cam.setup` | `part.CreateCamSetup("mill_planar")` 返回 `None`，`CAMSetup` 报 `no valid setup` |
| `cae.mesh` | `NXOpen.CAE` 绑定大、解算慢，未开始 |
| `asm.constraints` | 装配约束 API 未挖 |
| `export.dxf` | `DxfdwgCreator` 需要图纸上下文 |
| `export.stl` | `Commit()` 成功但 0 字节，需要 `ExportSelectionBlock` |
| `export.parasolid` | `Commit()` 报 `no valid export objects`，需要 `ExportSelectionBlock` |
| `drawing.projected_view` | `ProjectedViewBuilder.Parent` 只读 |
<!-- allow:pending:END -->

逐条证据见内核仓库
[`docs/PITFALLS.md`](https://github.com/Winterwind2017/nxkit/blob/main/docs/PITFALLS.md)
与 [`docs/UNSUPPORTED.md`](https://github.com/Winterwind2017/nxkit/blob/main/docs/UNSUPPORTED.md)。

## 典型任务配方

### 建模 + 体积判据

```bash
nxkit cap block.create      # 100×50×20 → 体积 100000、面 6、边 12
nxkit cap cylinder.create   # Ø40×30 → 37699.11
nxkit cap solid.cone        # Ø40×30 圆锥 → 12566.37
nxkit cap solid.sphere      # Ø40 球 → 33510.32
nxkit cap extrude.rect      # 矩形截面拉伸 → 50000
nxkit cap extrude.ring      # 带内孔截面 → 42000
```

### 特征（倒角/圆角/阵列/挖槽/钻孔）

```bash
nxkit cap feature.chamfer       # 一条边倒角 5 mm：面 7，体积 98000–100000
nxkit cap feature.edge_blend    # 一条边圆角 R5：面 7
nxkit cap feature.pattern_linear   # 沿 X 阵列 3 个：实体 3，体积 300000
nxkit cap feature.pattern_grid     # 2×2 阵列：实体 4，体积 400000
nxkit cap feature.pattern_circular # 圆周阵列 4 个：实体 4，体积 400000
nxkit cap feature.pocket        # 挖 40×20 通槽：84000
nxkit cap feature.hole_cyl      # 钻 Ø20 通孔：93716.815
nxkit cap feature.hole_array    # 四个 Ø20 通孔：74867.26
nxkit cap feature.shell         # 抽壳 2 mm：29344
```

### 草图

```bash
nxkit cap sketch.rect            # XY 平面草图 + 4 条线（自带 2 条参考线）
nxkit cap sketch.extrude         # 草图 4 线拉伸 10 → 50000
nxkit cap sketch.circle_extrude  # 草图整圆 R20 拉伸 30 → 37699.11
```

### 布尔

```bash
nxkit cap boolean.subtract  # A−B → 92000
nxkit cap boolean.union     # A∪B → 100000（B 在 A 内）
nxkit cap boolean.intersect # A∩B → 8000
nxkit cap boolean.two_tools # 一次减两个工具体 → 84000
```

### 装配

```bash
nxkit cap asm.add_component    # 插 1 个组件
nxkit cap asm.two_components   # 插 2 个并存盘
```

### 制图

```bash
nxkit cap drawing.sheet       # A3 图纸（297×420）
nxkit cap drawing.base_view   # Front 基础视图
```

### 导出

```bash
nxkit cap export.step   # 文件头 ISO-10303-21
nxkit cap export.iges   # .igs 落盘
nxkit cap export.acis   # .sat 落盘
```

### 属性 / 测量

```bash
nxkit cap attr.string   # 写字符串属性 → 存盘重开仍在
nxkit cap measure.mass  # 体积/面积/重心
nxkit cap measure.face_area # 六面面积和 16000
nxkit cap body.topo     # 面 6 / 边 12
```

## 交付前的自检三问

1. **数字变了吗？** 实体数/面数/边数/体积/面积/文件字节，至少一个有前后对比。
2. **落盘还存在吗？** 不只是"文件存在"：比大小、文件头（STEP `ISO-10303-21`）、
   重开后读数一致。
3. **负面对照做过吗？** 把关键参数换成已知错误值，判据必须失败。
   不能失败的判据，通常也证明不了成功。

## 需要细节时读这些

| 内容 |
|---|
| [`docs/PITFALLS.md`](https://github.com/Winterwind2017/nxkit/blob/main/docs/PITFALLS.md) |
| [`docs/UNSUPPORTED.md`](https://github.com/Winterwind2017/nxkit/blob/main/docs/UNSUPPORTED.md) |
| `references/pitfalls.md`（本技能侧，带最小复现） |
| `references/recipes.md`（完整配方与判据数字） |
| `references/checklists.md`（交付前清单） |
