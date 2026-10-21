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
4. `nxkit licenses` —— 读 SPLM `.dat`，确认本机买了这条能力需要的 feature
   （建模 `solid_modeling`、制图 `drafting`、装配 `assemblies`、其余 `gateway`）；
5. 动手前想清楚判据：这次改动应该让**实体数 / 面数 / 边数 / 体积 / 面积 /
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

共 **123** 条 verified 能力（内核 `nxkit 0.1.0`，commit `c96104f`，引擎 NX 2512）。完整状态：`nxkit list`；单条跑：`nxkit cap <id>`。

| 能力族 | 能力（级别） |
|---|---|
| **特征（拉伸）**（30） | `extrude.rect`（L1–L4） `extrude.ring`（L1–L3） `feature.boss`（L1–L3） `feature.chamfer`（L1–L3） `feature.chamfer_angle`（L1–L3） `feature.chamfer_edge`（L1–L3） `feature.chamfer_multi`（L1–L3） `feature.cross_hole`（L1–L3） `feature.edge_blend`（L1–L3） `feature.edge_blend_all`（L1–L3） `feature.extrude_taper`（L1–L3） `feature.hole_array`（L1–L3） `feature.hole_blind`（L1–L3） `feature.hole_csk`（L1–L3） `feature.hole_cyl`（L1–L3） `feature.mirror`（L1–L3） `feature.offset_face`（L1–L3） `feature.pattern_circular`（L1–L3） `feature.pattern_grid`（L1–L3） `feature.pattern_linear`（L1–L3） `feature.pocket`（L1–L3） `feature.pocket_blind`（L1–L3） `feature.revolve`（L1–L3） `feature.shell`（L1–L3） `feature.shell_volume`（L1–L3） `feature.spring`（L1–L3） `feature.stack_blocks`（L1–L3） `feature.sweep`（L1–L3） `feature.thicken`（L1–L3） `feature.tube`（L1–L3） |
| **sketch**（18） | `sketch.circle_extrude`（L1–L3） `sketch.collinear`（L1–L2） `sketch.concentric`（L1–L2） `sketch.constraint`（L1–L2） `sketch.dimension`（L1–L2） `sketch.equal_length`（L1–L2） `sketch.equal_radius`（L1–L2） `sketch.extrude`（L1–L3） `sketch.fixed`（L1–L2） `sketch.horizontal`（L1–L2） `sketch.linear_dim`（L1–L2） `sketch.midpoint`（L1–L2） `sketch.normal`（L1–L2） `sketch.parallel`（L1–L2） `sketch.perpendicular`（L1–L2） `sketch.rect`（L1–L2） `sketch.tangent`（L1–L2） `sketch.vertical`（L1–L2） |
| **制图**（12） | `drawing.base_view`（L1–L3） `drawing.second_sheet`（L1–L2） `drawing.sheet`（L1–L2） `drawing.sheet_a0`（L1–L2） `drawing.sheet_a1`（L1–L2） `drawing.sheet_a2`（L1–L2） `drawing.sheet_a4`（L1–L2） `drawing.sheet_ansi_a`（L1–L2） `drawing.sheet_ansi_b`（L1–L2） `drawing.sheet_ansi_c`（L1–L2） `drawing.view_isometric`（L1–L2） `drawing.view_scale`（L1–L2） |
| **属性**（10） | `attr.count`（L2） `attr.delete`（L2） `attr.double`（L2） `attr.int`（L2） `attr.logical`（L2） `attr.on_body`（L2） `attr.on_face`（L2） `attr.on_feature`（L2） `attr.string`（L2–L4） `attr.update`（L2） |
| **装配**（8） | `asm.add_component`（L1–L2） `asm.component_names`（L1–L2） `asm.constraint_refs`（L1–L2） `asm.five_components`（L1–L2） `asm.four_components`（L1–L2） `asm.nested`（L1–L2） `asm.three_components`（L1–L2） `asm.two_components`（L1–L4） |
| **曲线**（8） | `curve.arc`（L1–L3） `curve.ellipse`（L1–L3） `curve.helix`（L1–L2） `curve.hyperbola`（L1–L3） `curve.line`（L1–L3） `curve.offset`（L1–L2） `curve.parabola`（L1–L3） `curve.project`（L1–L2） |
| **实体**（8） | `block.create`（L1–L4） `block.two_bodies`（L1–L4） `cylinder.create`（L1–L4） `solid.cone`（L1–L3） `solid.cone_frustum`（L1–L3） `solid.scale`（L1–L3） `solid.sphere`（L1–L3） `solid.split_body`（L1–L3） |
| **布尔**（7） | `boolean.intersect`（L1–L4） `boolean.intersect_two`（L1–L3） `boolean.subtract`（L1–L4） `boolean.subtract_retain`（L1–L3） `boolean.two_tools`（L1–L3） `boolean.union`（L1–L4） `boolean.unite_three`（L1–L4） |
| **导出**（7） | `export.acis`（L1–L2） `export.iges`（L1–L3） `export.parasolid`（L1–L2） `export.step`（L1–L3） `export.step_ap203`（L1–L2） `export.step_ap214`（L1–L2） `export.stl`（L1–L2） |
| **测量**（5） | `measure.distance`（L2–L3） `measure.face_area`（L3） `measure.face_single`（L3） `measure.faces_two`（L2–L3） `measure.mass`（L3） |
| **部件**（4） | `datum.axis`（L1–L2） `datum.plane`（L1–L2） `part.inch`（L1–L3） `part.new`（L1） |
| **文件**（2） | `file.roundtrip`（L4） `file.save_copy`（L1–L4） |
| **拓扑检查**（2） | `body.topo`（L1–L3） `inspect.body_type`（L1–L2） |
| **surface**（2） | `surface.bounded_plane`（L1–L2） `surface.ruled`（L1–L2） |
<!-- gen:capabilities:END -->

## 还没打通（别重复试）

<!-- allow:pending:BEGIN -->
| 能力 | 卡在哪 |
|---|---|
| `feature.hole` | `HolePackageBuilder` 需要点位/面，未打通 |
| `drawing.dimension` | 线性尺寸 builder 的关联能设，`Commit()` 报 `Unable to create a dimension from the selected objects and annotation plane`；`Origin` 只读 |
| `measure.distance` | `MeasureDistance` 没有 `.Distance`，`Information()` 返回 `None` |
| `cam.setup` | **dead**：四种模板名全返回 None、`CAMSetup` 抛 1345023、`CAMDataManager` 只有 2 个曲线 builder |
| `cae.mesh` | `NXOpen.CAE` 绑定大、解算慢，未开始 |
| `asm.constraints` | 走到 ComponentPositioner，但 ConstraintCollection.CreateConstraint 不存在 |
| `feature.rib` | `part.Features` 上没有 `CreateRibBuilder` |
| `feature.sweep` | `CommitFeature` 报 `Unable to approximate guide string` |
| `feature.chamfer_angle` | `ChamferBuilder.Option`/`AngleExp` 赋值无效 |
| `sketch.constraints`（其余类型） | 重合已通，水平/竖直/相切/尺寸未逐个验证 |
| `export.dxf` | `DxfdwgCreator` 需要图纸上下文 |
| `export.parasolid` | 四种方式全报 `no valid export objects` |
| `feature.thicken` | 出 2 个片体或厚度变 3300 mm，语义不对 |
| `drawing.projected_view` | ParentViewBuilder.View 不可写 |
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
nxkit cap solid.scale       # 整体缩放 2× → 800000
nxkit cap solid.cone_frustum # 圆台 底Ø40/顶Ø20/高30 → 21991.15
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
nxkit cap feature.hole_blind    # 盲孔 Ø20 深 10：96858.41
nxkit cap feature.hole_csk      # 沉头孔 Ø20 通 + Ø30 深 5：91753.32
nxkit cap feature.boss          # 圆柱凸台 Ø20×10（并集）：103141.59
nxkit cap feature.extrude_taper  # 拉伸 10 带 5° 拔模：48697.88
nxkit cap feature.cross_hole    # 横向 Ø20 通孔：68584.07
nxkit cap feature.offset_face  # 六面偏置 5 mm：198000
nxkit cap feature.stack_blocks # 两块叠加并集：115000
nxkit cap feature.pocket_blind  # 盲槽 40×20 深 10：92000
nxkit cap feature.mirror       # 以面为镜像平面 → 2 实体 200000
nxkit cap feature.shell_volume  # 抽壳 2 mm 后体积 29344
nxkit cap feature.shell         # 抽壳 2 mm：29344
nxkit cap feature.revolve       # 矩形绕 Z 转 360°：37699.11
nxkit cap feature.edge_blend_all # 全边圆角 R3：26 面
nxkit cap feature.chamfer_edge  # 另一条边倒角：面 7
nxkit cap feature.tube          # 直线做 Ø20 管：31415.93
```

### 草图

```bash
nxkit cap surface.bounded_plane  # 4 条线围成有界平面片体
nxkit cap sketch.rect            # XY 平面草图 + 4 条线（自带 2 条参考线）
nxkit cap sketch.extrude         # 草图 4 线拉伸 10 → 50000
nxkit cap sketch.circle_extrude  # 草图整圆 R20 拉伸 30 → 37699.11
nxkit cap sketch.constraint      # 两条线加重合约束
nxkit cap sketch.horizontal      # 水平约束
nxkit cap sketch.vertical        # 竖直约束
nxkit cap sketch.equal_length    # 等长约束
nxkit cap sketch.perpendicular   # 垂直约束
nxkit cap sketch.dimension       # 整圆直径尺寸 50
nxkit cap sketch.linear_dim      # 两线间竖直尺寸 40
nxkit cap sketch.fixed           # 固定约束
nxkit cap sketch.collinear       # 共线约束
nxkit cap sketch.concentric      # 同心约束
nxkit cap sketch.midpoint        # 中点约束
nxkit cap sketch.parallel        # 平行约束
nxkit cap sketch.equal_radius    # 等半径约束
nxkit cap sketch.tangent         # 相切约束
nxkit cap drawing.sheet_a0       # A0 图幅（1189×841）
nxkit cap drawing.sheet_a1       # A1 图幅（841×594）
nxkit cap drawing.sheet_a2       # A2 图幅（594×420）
nxkit cap drawing.sheet_ansi_a   # ANSI A（8.5×11 in）
nxkit cap drawing.sheet_ansi_b   # ANSI B（11×17 in）
nxkit cap drawing.sheet_ansi_c   # ANSI C（17×22 in）
```

### 布尔

```bash
nxkit cap boolean.subtract  # A−B → 92000
nxkit cap boolean.union     # A∪B → 100000（B 在 A 内）
nxkit cap boolean.intersect # A∩B → 8000
nxkit cap boolean.two_tools # 一次减两个工具体 → 84000
nxkit cap boolean.unite_three # 三体并集 → 115000
nxkit cap boolean.intersect_two # 一次交两个工具体 → 12000（交的是工具并集）
```

### 装配

```bash
nxkit cap asm.add_component    # 插 1 个组件
nxkit cap asm.two_components   # 插 2 个并存盘
nxkit cap asm.three_components # 插 3 个
nxkit cap asm.four_components  # 插 4 个
nxkit cap asm.nested           # 子装配嵌套（外层 2 节点）
nxkit cap asm.five_components  # 插 5 个
nxkit cap asm.component_names  # 组件名保留（AAA/BBB/CCC）
nxkit cap asm.constraint_refs  # 建约束 + 两个面参考（参数顺序反着传）
```

### 制图

```bash
nxkit cap drawing.sheet       # A3 图纸（297×420）
nxkit cap drawing.base_view   # Front 基础视图
nxkit cap drawing.sheet_a4    # A4：210×297
nxkit cap drawing.view_isometric # 等轴测视图 Isometric@1
```

### 导出

```bash
nxkit cap export.step   # 文件头 ISO-10303-21
nxkit cap export.iges   # .igs 落盘
nxkit cap export.acis   # .sat 落盘
nxkit cap export.stl    # .stl（需 ExportSelectionBlock.Add(bodies)）
```

### 属性 / 测量

```bash
nxkit cap attr.string   # 写字符串属性 → 存盘重开仍在
nxkit cap measure.mass  # 体积/面积/重心
nxkit cap measure.face_area # 六面面积和 16000
nxkit cap measure.faces_two  # 只量两个大面（10000）
nxkit cap measure.distance   # 两面间距 20（MeasureDistance.Value）
nxkit cap measure.face_single # 最大面 5000 / 周长 300
nxkit cap body.topo     # 面 6 / 边 12
nxkit cap inspect.body_type # 块=solid、有界平面=sheet
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
