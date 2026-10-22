# nxkit 收口报告

引擎 **NX 2512**（`D:\Program Files\Siemens\DesigncenterNX2512`），内核 **nxkit 0.1.0**，技能 **ww-nx-automation**。

## 1. 结果

| 指标 | 数值 |
|---|---|
| 真机通过能力 | **144** |
| 其中带 L4（存盘→重开→复测） | **54** |
| 一次会话跑完全部能力 | ~56 s（DXF+DWG 两次翻译器各约 17 s） |
| 未打通（每条都有 NX 原文错误） | **15** |

### 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 33 | 29 |
| sketch | 18 | 2 |
| drawing | 14 | 0 |
| attr | 10 | 2 |
| solid | 10 | 8 |
| curve | 9 | 0 |
| assembly | 8 | 1 |
| boolean | 7 | 7 |
| export | 7 | 0 |
| inspect | 6 | 0 |
| measure | 6 | 2 |
| surface | 6 | 1 |
| part | 4 | 1 |
| file | 2 | 1 |

## 2. 怎么做的

### 2.1 一个会话只跑一次 NX

主机侧生成一个 job（JSON）→ `run_journal.exe journal.py -nx` 一次拉起 NX → `nxkit.runtime.actions` 逐条能力造几何/读读数 → 主机侧判分。NX 的退出码恒为 1，**只认 `result.json`**。

### 2.2 判据全部从 NX 读回

四层：L1 计数（体/面/边/视图）、L2 属性（体积/面积/长度/间距）、L3 几何关系（体积守恒、面积回归、距离）、L4 存盘→重开→复测。容差按量级分档：≥100 → 0.5，≥1 → 1e-3，其余 1e-6。

### 2.3 批量探针（本轮最大的效率杠杆）

一个探针脚本在一次 NX 会话里试 4–6 个 builder × 多组参数，输出一行 `BATCHn <json>`。早期是「一个变体一次会话（~25 s）」，探针把节奏提到「一次会话 6 个变体」，本轮 130 → 140 条基本靠它。

### 2.4 新增能力只走 `tools/add_cap.py`

锚点插入（`\nACTIONS = {` / `ACTIONS = {\n` / `CAPS: tuple[Cap, ...] = (\n`）+ `py_compile` + `selftest`。历史上用正则「删到下一个 def」把 `ACTIONS` 整块删掉过 6 次。

## 3. 判死的 15 项（按卡点分类）

### （a）需要服务对象，NX 不给工厂

- **`curve.intersection`**：`FirstFace/SecondFace` 只读，`FirstSet/SecondSet` 收对象但 Commit 报 `No objects for intersection curve`；用**组合投影**替代已打通（`curve.combined_projection`）
- **`curve.bridge`**：`BridgeCurveBuilder.StartObject/EndObject` **不可写**，直接 `CommitFeature()` 报 `Cannot create bridge.`（与 curve.intersection 同类）
- **`pattern.body_linear`**：`CreatePatternBodyBuilder(PatternBody.Null)` 能建，`SelectBody.Value = body` 也接受；但 `ReferencePoint` 是 `PatternReferencePointServiceBuilder`（不是选择集），不设它 Commit 报 `Incorrect object for this operation`

### （b）入口只读 / 没有写入通道

- **`solid.move_body`**：`ModlMotion` 参数全设上、两个 Commit 都成功但几何不动；`FreeTransformerBuilder`/`MeshTransformerBuilder` 只吃**面/曲线/点**，没有目标体入口（Commit 报 `Missing target body.`）
- **`solid.delete_body`**：`BodyToDelete` 构造出来是 `None`；赋一个 `ScCollector` 后 `CommitFeature()` 返回成功，但**体仍在**（`removed=0`）→ 空操作。删面（`solid.delete_face`）已打通，可作为替代
- **`drawing.section_view`**：`CreateSectionViewBuilder(base_view)` 报 `Invalid object type for this operation`；用 `SectionView.Null` 能构造，但 `ParentView` **不可写**、`Commit()` 报 `Null tag not allowed`
- **`feature.revolve_datum`**：`RevolveBuilder.Axis` 只认 `NXOpen.Axis`：给 `DatumAxis` 报 `Expecting NXOpen.Axis type, found NXOpen.DatumAxis`。所以"基准特征当几何输入"这个范式**只对 Face/Plane 成立，对 Axis 不成立**
- **`feature.text`**：`TextBuilder.TextString` 可设、`PlacementFaces` 可喂，但 `PlanarFrame.CoordinateSystem` 无入口：`CoordinateSystemCollection.CreateCoordinateSystem` 的参数签名对不上（`No overload matches these arguments`），Commit 恒报 `Reference coordinate sys

### （c）控制器空转（参数全设、Commit 成功、几何不动）

- **`asm.constraints`**：见 UNSUPPORTED.md
- **`sketch.point_on_curve`**：约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10）

### （d）NX 直接拒建

- **`sketch.slope / sketch.constant_angle / sketch.constant_length`**：见 UNSUPPORTED.md
- **`feature.chamfer`**：`CreateChamferBuilder(...).SmartCollector` 是 **None**，没有可写的边集合；直接 `CommitFeature()` 报 `Referenced edge does not exist`
- **`feature.chamfer_angle`**：`ChamferBuilder.Option` / `AngleExp` 赋值后读回仍是默认（对称偏移），角度模式设不上；对称倒角已由 `feature.chamfer_edge` 覆盖
- **`sheet_metal.flange`**：`SilhouetteFlangeBuilder`：`BaseCurves`(Section) 与 `BaseFaces`(scCollector) 都能喂，`ReferenceVector` 也接受 Direction，但方向取 (0,0,1) 报 `Unable to project base curves to base faces.`，取 (0,1,0)/(1,0,0) 报 `Unable to create silhouett

### （e）环境缺表 / 缺模块

- **`cam.setup`**：`part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder
- **`cae.mesh`**：`NXOpen.CAE` 绑定 16 MB，起解算耗时长

### （f）旧路径不可用（已用 CLI 替代）

- **`export.dxf / export.dwg`**：见 UNSUPPORTED.md

## 4. 替代方案（打通的那条路）

| 原本要 | 改用 | 能力 id |
|---|---|---|
| 交线 `curve.intersection` | 已直接打通（ScCollector + Tolerance） | `curve.intersection` |
| 实体阵列 `PatternBody` | 换 `PatternFeatureBuilder`（阵列特征） | `feature.pattern_linear` |
| 片体偏置 `OffsetSurfaceBuilder` | `VariableOffsetBuilder` | `surface.offset` |
| 删实体 `delete_body` | 删面愈合 | `solid.delete_face` |
| 投影视图 builder | `SheetDraftingViews.CreateProjectedView` | `drawing.projected_view` |
| 关联式线性标注 | `MeasureManager.CreateDimensionAnnotation` | `drawing.dimension` |

## 5. 复现

```powershell
$env:PYTHONPATH='D:\bililive\nxkit\src'
python -m nxkit run --workdir D:\bililive\nxkit\_runs\check
# → 140/140 通过（一次会话，约 19 s）
python -m nxkit selftest      # 离线自检：动作/判据齐全、负例被拒
python -m pytest -q tests     # 9 个离线测试
python tools\check_consistency.py --skill D:\bililive\ww-nx-automation
```

## 6. 已知边界

- 只在本机 NX 2512 + 4,420 特性的许可下验证过；
- `run_journal` 退出码恒 1，不要用退出码判断成败；
- 装配求解、剖视图、实体阵列这几类**依赖交互式选择**的功能，journal 下拿不到求解器/选择上下文；
- `export.dxf` 会死循环，永久禁用。
