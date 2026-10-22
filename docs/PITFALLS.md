# 坑清单（NX 2512 实测）

> 每条都来自本机真机探针（`_nx_recon/probe_*.py`）。改代码前扫一遍。

## 一、builder 的 Null 哨兵各不相同

| 场景 | 正确写法 | 传错的表现 |
|---|---|---|
| 建块/圆柱/拉伸 | `part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)` | — |
| 布尔 | `CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)` | `TypeError: Expecting NXOpen.Features.BooleanFeature type, found Feature` |
| 基础视图 | `DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)` | `TypeError: Expecting NXOpen.Drawings.BaseView type` |

## 二、集合/属性没有想象中好用

| 现象 | 实测 | 用法 |
|---|---|---|
| `len(part.Bodies)` / `part.Bodies[0]` / `.ToArray()` | 全不支持（`BodyCollection` 只有 `FindObject`） | 从 `feature.GetBodies()` 拿 |
| 布尔后实体被"数了三次" | `Block(0)`、`Block(1)`、`Subtract(2)` 都指向同一个结果体 | 按 `b.Tag` 去重 |
| `part.PartUnits` | `int()` 抛错，`str()` 给 `'1'` | `str(...) in ("1","Millimeters")` |
| `part.ModelingViews.WorkView` | 插图纸后报 "The view is not a model view" | 遍历 `part.ModelingViews` 按名字取 |

## 三、拉伸/截面

- `CreateSectionsUsingCurves(curves, loop_option, chain_tol, dist_tol, angle_tol)`
  —— **5 个参数**，少一个报 `Function takes 5 arguments, 4 passed`。
- 带内孔截面用 `LoopOption.SeparateOuter`（`Separate` 会把内环当独立截面）。
- 拉伸距离：`Limits.StartExtend.SetValue(0.0)` / `EndExtend.SetValue(d)`；
  `StartExtend.Value` 是 `Expression`，**直接赋值 `Value` 会报只读**。
- `ExtrudeBuilder.Limits` 的实际类型是 `LinearLimits`，成员只有
  `StartExtend / EndExtend / SymmetricOption / Null / Tag / Validate`。

## 四、出图

- `InsertSheet(name, StandardSheetSize.A3, 1.0, 1.0, ProjectionAngleType.FirstAngle)`
  （枚举是 `FirstAngle`/`ThirdAngle`，**不是** `First`）。
- 基础视图必须给 `SelectModelView.SelectedView` 一个 `ModelView`
  （可选名：Top/Front/Right/Back/Bottom/Left/Isometric/Trimetric）。
- `ViewPlacementBuilder.Placement` 只读；不设位置就让它自动摆放。

## 五、导出

- 没有 `part.Export*`；导出走 `session.DexManager`：
  `CreateStepCreator()` / `CreateIgesCreator()` → 设 `OutputFile` → `Commit()`。
- 直接 `NXOpen.StepCreator()` 构造会 `Invalid self parameter passed`。

## 六、文件与进程

- `part.SaveAs(path)` 目标已存在 → `NXException: File already exists`，先删。
- 重开：`parts.OpenActiveDisplay(path, DisplayPartOption.AllowAdditional)`
  返回 **tuple**（`(BasePart, PartLoadStatus)`）。
- `run_journal` 即使全成功也可能返回 **退出码 1**；以 `result.json` 为准。
- `part.Close(CloseWholeTree.TrueValue, CloseModified.CloseModified, None)`。

## 七、许可证

- 反编译 `UF_MODL_create_block1` 看到每次调用都
  `JAM_start_uf_call` → `JAM_reserve_uf_license("solid_modeling")` → `UFX_*`。
  许可证不足时函数返回非 0、几何不动。
- 本机 `.dat` 有 **4,422 个 feature**（`solid_modeling`/`assemblies`/`drafting`/
  `cam_base`/`cam_advanced`/`sheet_metal`/`iges`/`dxf` 等都在）。
- `LicenseManager.CheckPresence("measure")` 返回 false **不代表**测量不可用
  （测量在 bundle 里，名字不是 "measure"）。判断可用性用实际调用。

## 八、Python 绑定是子集

- `ufs.Modl` 只有 213 个方法（原生 `UF_MODL_*` 815 个），`CreateBlock1` 不在里面。
- 建块/拉伸走 `NXOpen.Features`；UF 只在有绑定时用。
- `NXBIN\python` 里没有 `python.exe`，解释器嵌在 NX 里，只能 `run_journal -py`。

## 九、改代码时的自伤（2026-10-21 真踩）

- 用"从 `def X` 删到下一个 `def`"的方式删函数，**把夹在中间的 `ACTIONS` 字典一起删了**，
  于是 22 条能力全部 `KeyError`、整会话 0 通过；而 `selftest` 只检查
  `def X(` 是否存在，**照样通过**。
- 修法：`selftest` 与 `tests/test_offline.py` 现在同时检查
  `"动作": 函数,` 是否登记进 `ACTIONS`。删代码后先跑 `pytest` 再跑真机。
- `MeasureDistance` 没有 `.Distance`；`Information()` 返回 `None`。别对着它写判据。
- `MeasureManager.MeasureType` 的成员是 `Minimum`/`Maximum`，**不是** `MinimumDistance`。
- `part.CreateCamSetup("mill_planar")` 返回 `None` 且不建 setup（`CAMSetup` 报
  "Current part does not contain valid setup"）。

## 十、选择意图：chamfer / edge blend / pattern（2026-10-21 打通）

- **`SmartCollector` 是 None**：`CreateChamferBuilder(...)` 自带的 collector 读出来是 None，
  必须先自己建一个再**赋值**回去：
  ```python
  sc = part.ScCollectors.CreateCollector()
  rule = part.ScRuleFactory.CreateRuleEdgeDumb([edge])   # 不是 CreateRuleCurveDumb
  sc.AddRules([rule])                                     # ScCollector 没有 Add
  cb.SmartCollector = sc
  ```
- **圆角**：`CreateEdgeBlendBuilder(Feature.Null)` + `eb.AddChainset(sc, "5")` + `CommitFeature()`。
- **矩形阵列**：`pb.FeatureList.Add([feat])`；`rd = pb.PatternService.RectangularDefinition`；
  `rd.XDirection = part.Directions.CreateDirection(Point3d, Vector3d(1,0,0), UpdateOption.WithinModeling)`；
  `rd.XSpacing.NCopies.SetFormula("3")`、`rd.XSpacing.PitchDistance.SetFormula("120")`。
  `NCopies` 是 **Expression**（直接赋 int 报只读），默认 2 个实例。
- 三条都只动一个/一组具体边，判据看 **面数**（+1）与 **体积区间**。

## 十一、单边倒角的体积随"选中哪条边"变化

同一份 `chamfer_edge` 代码，体积可能读出 **99750 / 99375 / 98750** —— 因为
`body.GetEdges()` 的顺序不稳定，选中的边长度可能是 20/50/100 mm：
`V_removed = 0.5 × 5 × 5 × L`。判据必须给区间（本项目用 98500–100000），
不能写死一个数。同类问题也出现在 `chamfer_multi`（面数 10~12）。

## 十二、拉伸拔模：`Draft.DraftOption` 要枚举，不是 1

`ExtrudeBuilder.Draft` 是 `MultiDraft`，`DraftOption` 必须给
`NXOpen.GeometricUtilities.SimpleDraft.SimpleDraftType.SimpleFromStart`
（传 `1` 报 "First parameter is invalid"）。只设 `DraftAngle = 5` 而 `DraftOption`
仍是默认时，**体积一丝不变**（50000 → 仍然是 50000），是"假成功"的典型。
设好之后 100×50×10 带 5° 拔模 = **48697.8757**。

## 十三、布尔后的"零体积幽灵实体"

`feature.cross_hole`（管道求差）体积正确（68584.07），但 `_bodies_of` 数出 **2 个实体**：
第二个实体体积为 0（被消耗的工具体的残留记录）。`RetainTool=False` + `RetainTarget=True`
反而变成 3 个实体、体积翻倍（100000 + 68584），更糟。
处理方式：这类复合能力**不判 body_count**，只判体积（并保留 body_count 在 reads 里备查）。

## 十四、DXF 导出：NXOpen 是空操作，翻译器 CLI 才行

**旧结论（已推翻）**：`CreateDxfdwgCreator()` + `Commit()` 会死循环。

拆开看是两件事：

1. **不设 `SettingsFile`** → `Commit()` 死循环（656 s CPU，需 taskkill）；
2. **设了 `SettingsFile`**（`<NX>\DXFDWG\dxfdwg.def`）→ `Commit()` 立刻返回、**不写任何文件**，
   连翻译器 log 都不产生；`ExportData/ExportAs/OutputTo/ExportFrom/DrawingList/
   UGI_DRAWING_NAMES` 全试过，仍是空的。→ NXOpen 这条路在 journal 里不可用。

**能用的路**：直接起 NX 自带翻译器 CLI：

```text
<NX>\NXBIN\dxfdwg.exe <part.prt> o=<out.dxf> l=<log> d=<def> m=ugtodxf
```

- `<def>` 用 `<NX>\DXFDWG\dxfdwg.def` 的副本，把 `UGI_DRAWING_NAMES =` 改成
  `UGI_DRAWING_NAMES = S1`（**默认空 = 什么都不导**），`LOG_FILE` 指到可写路径；
- 输入必须是**已存盘的 .prt**（含图纸与视图），所以先 `SaveAs`；
- 实测 100×50×20 块 + A3 + Front 视图 → **190 KB DXF**，log 记
  `Line 16 / View Port 2 / Layout 6`；
- 从 journal 里 `subprocess.run(..., timeout=180)` 调它即可，整条能力约 15 s（翻译器启动占大头）。

→ `export.dxf` 现在是**已验证能力**；`export.dwg` 同一条 CLI 换 `m=ugtodwg`，尚未单独验证。

## 十五、代码手术纪律（血泪版）

本轮为了删一个函数，用了两类危险操作，都造成了真实损坏：

1. **正则按行删 `"name": name,`** —— 本意是清理 ACTIONS 条目，结果把函数体里
   `"body_count": 1,`、`"activated": activated,` 这类**普通字典行**一起删了，
   5 条能力静默失败；
2. **"删到下一个 def / 删到 ACTIONS"** —— 已经三次把 `ACTIONS` 字典本身吞掉。

定规：
- 删函数用 `ast` 解析取 `FunctionDef` 的 `lineno/end_lineno` 精确切片，或**从 git 恢复**再重做；
- 任何批量文本替换后，**先 `py_compile` + `nxkit selftest`，再跑真机**；
- 修坏了先 `git checkout HEAD -- <file>`，别在破损文件上继续打补丁。

## 十六、ANSI 图幅读回是**英寸**，ISO 图幅是**毫米**

同一个 `InsertSheet(...)`，`sheet.Height/Length` 的单位跟着图幅系列走：
- `A4/A3/A2/A1/A0` → **毫米**（如 A4 = 210 / 297）
- `A/B/C/D/E`（ANSI）→ **英寸**（如 A = 8.5 / 11，B = 11 / 17）

判据必须按系列给单位，否则 A 图幅会"差 25.4 倍"。

## 十七、`Part.Units` 枚举值是 0/1，不是 1/2

`part.PartUnits` 读回字符串 `"0"` 表示 **Inches**，`"1"` 表示 **Millimeters**
（`NXOpen.Part.Units.Inches == 0`）。判单位别用 "1/2"，会一直判错。
另外英制部件里 `mass()` 的体积/面积是**部件单位**（in³ / in²），
4×2×1 in 的块读回 8.0，不是 13109.7 mm³。

## 十八、STEP 的协议可以从 schema 读出来

`StepCreator.ExportAs = ExportAsOption.Ap214` 后，文件里会出现
`FILE_SCHEMA(('AUTOMOTIVE_DESIGN'...))`；AP203 是 `CONFIG_CONTROL_DESIGN`。
所以"我真的导出了 AP214"可以**读文件内容**验证，不必信返回值。

## 十九、加厚后片体不会消失，体积要把片体排除掉

`ThickenBuilder` 成功后会**保留原来的片体**并新增一个实体：
`_bodies_of(part)` 数出 2 个，若把两者一起拿去算质量，片体贡献 0 体积、
但会把 `body_count` 判据带偏（早期版本就是这么误判成"2 个片体、体积 0"）。
正确做法：`solids = [b for b in bodies if b.IsSolidBody]` 再 `mass(part, solids)`。
100×50 的片体加厚 5 mm → 实体体积 **25000**，`FirstOffset` 默认值是 2.5。

## 二十、`ComponentPositioner.EstablishNetwork()` 会让 journal 会话直接崩掉

在装配里调用它，`run_journal` 整个会话中断（没有 result.json、判"会话中断"）。
求解装配约束只能靠 `EndAssemblyConstraints()`；`EstablishNetwork`/`ClearNetwork`
在脚本里属于危险接口，不要调用。

## 二十一、Parasolid 导出的真正开关是 `ObjectTypes.Solids`

`CreateParasolidExporter()` 即使设了 `ExportFrom = DisplayedPart`，默认 `ObjectTypes`
全部为 False，`Commit()` 会报
`Part has no valid export objects or all valid export objects are filtered out.`。
必须显式打开类别：

```python
ex.ExportFrom = NXOpen.ParasolidExporter.ExportFromOption.DisplayedPart
ex.ObjectTypes.Solids = True      # ← 缺这句就永远"没有可导对象"
ex.OutputFile = path
ex.Commit()
```

导出的 `.x_t` 头两行是 `**ABC...` 与 `**PARASOLID ...`，所以**判据要读前 200 字节**，
只读 64 字节会漏掉关键字（本项目就漏过一次）。

## 二十二、镜像的 `Plane` 要的是"平面对象/面"，不是 `part.Planes` 造出来的 Plane

`MirrorFeatureBuilder.Plane` 是 `SelectObject`，可以 `Plane.Value = obj`，但：

- `Plane.Value = part.Planes.CreateFixedPlane(...)` → 赋值不报错、`CommitFeature()` 报
  `No plane to Mirror about.`
- `Plane.Value = body.GetFaces()[0]`（一个**平面面**）→ 通过，镜像出 2 个实体

所以脚本里做镜像时，直接用模型上的平面面当镜像平面最省事；
`NXOpen.Features.DatumPlane` 这个哨兵在本机不存在（`CreateDatumPlaneBuilder` 在，
但 `DatumPlane.Null` 拿不到）。

## 二十三、判据容差必须按量级给，不能一刀切 0.5

`judges._close` 早期对所有数值用 `ABS_TOL = 0.5`，结果
`drawing.view_scale` 读回 0.590012、期望 0.5，差 0.09 ≤ 0.5，**判通过**——
比率类判据等于没有。现在按量级收紧：

| |want| 量级 | 容差 | 适用 |
|---|---|---|
| ≥ 100 | 0.5 | 体积（mm³）、面积（mm²） |
| ≥ 1 | 1e-3 | 尺寸、计数 |
| < 1 | 1e-6 | 比例、系数 |

收紧后全量重跑仍是 114/114，说明没有别处靠宽容差混过去。

## 二十四、图纸的 Length 是长边、Height 是短边

`DrawingSheet.Length` / `Height` 不是"宽/高"的字面含义：A4 横放时
`Length = 297`、`Height = 210`。判据写 `height=297, width=210` 会失败，
正确是 `current_height=210, current_width=297`。

## 二十五、视图比例的 `Numerator/Denominator` 是相对自动缩放的

`vb.Scale.Numerator = 1, Denominator = 2` 之后，`view.Scale` **不是 0.5**，
而是"自动缩放值的一半"（A3 + 100×50×20 块：0.590012 → 0.295006）。
所以判据要**自校准**：同一模型建两个视图（自动 + 1:2），比较
`ratio_scale * 2 ≈ auto_scale`，别硬编码 0.5。

## 十六、只读属性返回的选择对象是可写的（一次性误判了 3 条能力）

`BridgeCurveBuilder.StartObject` / `IntersectionCurveBuilder.FirstFace` /
`SectionViewBuilder.ParentView` 这类属性**本身**不可赋值：

```python
bcb.StartObject = c1          # AttributeError: not writable  ← 我卡在这里很久
bcb.StartObject.Value = c1    # ✅ 属性只读，但它包着的 SelectObject/ScCollector 可写
```

同理：
- `icb.FirstFace` / `SecondFace` 是 **ScCollector** → `AddRules([CreateRuleFaceDumb([face])])`；
- 交线还要求 `icb.Tolerance > 0`，否则 `Distance Tolerance cannot be zero.`；
- 桥接产物是 **Spline**，没有 `StartPoint`；`GetDefiningPoints()` 返回 `[None]`，
  要用 **`Get3DPoles()`**（首末极点即端点）。

→ 结论：遇到 "property not writable" 先看 `type(prop).__name__`，是
`SelectObject`/`ScCollector`/`Section` 就改成写它的 `.Value` / `.AddRules` / `AddToSection`。

## 十七、"实体阵列"走错了 builder（PatternBody → PatternFeature）

`PatternBodyBuilder` 在 journal 里两条路都死：显式给 `ReferencePoint.Point` 报
`Each patterned body must be face coincident with another patterned body.`，
不给则 `Incorrect object for this operation.`

换成 **`PatternFeatureBuilder`（阵列特征）** 就能真出几何：

```python
pb = part.Features.CreatePatternFeatureBuilder(PatternFeature.Null)
pb.FeatureList.Add([block_feature])          # 是 SelectObjectList
pd = pb.PatternService                       # 注意：它本身就是 PatternDefinition
pd.PatternType = PatternDefinitionPatternEnum.Linear
xsp = pd.RectangularDefinition.XSpacing      # DistancePatternSpacing
xsp.SpaceType = PatternSpacingSpacingType.Pitch
xsp.NCopies.SetFormula("3")
xsp.PitchDistance.SetFormula("150")
pb.CommitFeature()                           # → 3 个体，体积 300000
```

教训：一个"族"里有多个 builder 时，别在第一个上死磕；先列出
`Create*Pattern*Builder` 的全部入口（Python 绑定里还有 PatternGeometry /
PatternFace / PatternFaceFeature / CombinePattern），逐个试哪个接受你的输入。

## 十八、移动实体：MoveBody 的 DeltaXyz 是空操作，Distance 才动

```python
b = part.Features.CreateMoveBodyBuilder(NXOpen.Features.MoveBody.Null)   # 哨兵是 MoveBody
b.BodyToMove.AddRules([part.ScRuleFactory.CreateRuleBodyDumb([body])])

# 空操作：CommitFeature() 成功，但重心一点没变
m.Option = ModlMotionOptions.DeltaXyz; m.DeltaXc.SetFormula("100")

# 真的动：重心 50 → 150
m.Option = ModlMotionOptions.Distance
m.DistanceVector = part.Directions.CreateDirection(..., +X, ...)
m.DistanceValue.SetFormula("100")
```

`ModlMotionDelta` 的成员是 `ReferenceWcsWorkPart` 之类（参考坐标系），不是 XYZ 分量。
判据必须读重心/体积，不能只看 Commit 是否报错。
