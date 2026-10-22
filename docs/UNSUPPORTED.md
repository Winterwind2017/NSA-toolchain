# 未支持 / 未验证

状态说明：`dead` = 试过且不可行；`pending` = 还没做；`external` = 依赖本机之外。

## dead

| 能力 | 真机证据 |
|---|---|
| `cam.setup` | `part.CreateCamSetup(...)` 四种模板名全返回 None；`part.CAMSetup` 抛 1345023；`CAMDataManager` 只有 2 个曲线 builder |
| `DxfdwgCreator.Commit()`（旧路径） | journal 里**静默空操作**：不设 `SettingsFile` 时死循环；设了之后 `Commit()` 立刻返回但不写任何文件（连翻译器 log 都不产生）。已改用翻译器 CLI（`NXBIN` 下的 `dxfdwg.exe`） | 已替代 |

## pending（按依赖顺序）

| 能力 | 卡在哪（真机证据） | 依赖 |
|---|---|---|
| `cae.mesh` | `NXOpen.CAE` 绑定 16 MB，起解算耗时长 | 许可证 `simulation`（本机有） |
| `asm.constraints`（解算） | 已把整套流程走通：`Positioner.BeginAssemblyConstraints()` → `CreateConstraint(True)` → `ConstraintType=Touch` → 两个 `CreateConstraintReference`（成功，返回 `ConstraintReference`）→ `LoadConstraintGeometry` → `EndAssemblyConstraints()`（返回 None）→ `SolvePostponedConstraints()`（返回 None）。但**两面距离在解算前后都是 10.0**、`GetConstraintStatus()` 恒为 0 → 约束没解算 | 需要交互式约束求解器 |
| `sketch.constant_length` | `CreateConstantLengthConstraint(geom)` 报 `Unable to create sketch geometric constraint`（可能要配表达式/尺寸）。**语义相近但不等于**：`sketch.equal_length` 做的是「两线等长」，constant length 是「单条曲线长度锁定」 | 需要正确签名 |
| `sketch.constraints`（其余类型） | 重合/水平/竖直/等长/垂直/固定 已通；相切、中点、共线等未逐个验证 | 逐步加 |
| `drawing.section_view` | `CreateSectionViewBuilder(base_view)` 报 `Invalid object type for this operation`；用 `SectionView.Null` 能构造，但 `ParentView` **不可写**、`Commit()` 报 `Null tag not allowed` | 需要剖切线先建（`SpecifySectionLineBuilder`）且父视图入口不可写 |


## external

（暂无。）


| `solid.delete_body` | `CreateDeleteBodyBuilder(DeleteBody.Null)` 能构造，但 **`BodyToDelete` 与 `BodyToKeep` 两个 collector 运行时都是 `None`**（喂 `AddRules` 报 `NoneType has no attribute AddRules`）；直接 `CommitFeature()` 报 `Missing target body.`。**部分覆盖**：`solid.delete_face`（删面愈合）/ `solid.trim_body` / `boolean.subtract` 可交付大部分「去掉一块几何」的需求 | 服务对象未初始化 |




| `sketch.point_on_curve` | 约束能建（`CreatePointOnCurveConstraint` + `ConstraintGeometry.PointType=StartVertex` 都接受），但 `Sketch` 没有 `Solve()`，`Deactivate(view, UpdateLevel.Model)` 之后几何**没有移动**（端点仍在 y=10） | 需要正确的求解触发方式 |

| `sketch.slope` / `sketch.constant_angle` / `sketch.constant_length` | 三个 API 都能调，但一律返回 `Unable to create sketch geometric constraint.`（同族的 normal / tangent / parallel 都能建）→ 这几个类型可能在 journal 下不可用 | 需要 UI 上下文或前置条件 |





| `sheet_metal.flange` | `SilhouetteFlangeBuilder`：`BaseCurves`(Section) 与 `BaseFaces`(scCollector) 都能喂，`ReferenceVector` 也接受 Direction，但方向取 (0,0,1) 报 `Unable to project base curves to base faces.`，取 (0,1,0)/(1,0,0) 报 `Unable to create silhouette flange with given reference vector.` | 需要交互式选面/选向 |
