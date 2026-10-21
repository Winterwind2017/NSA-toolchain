# 静默失败清单（Silent Failures）

> SolidWorks 2025 SP4.1（33.4.1）实测，2026-10-21。
> 本文记录本仓库**已登记但未达可用**的项，重点是"为什么不通"，而不是"没试过"。

## 为什么单独写这一份

SolidWorks API 最常见、也最坑的一类失败**不是报错**，而是：

> 调用成功返回（`True` / 一个 `Feature` 对象 / 一个体对象），**但模型完全没有变化**。

如果判据只看"返回非空"或"特征数 +1"，就会把它当成成功——这叫**假成功**。
本仓库所有 verified 工具的判据一律是**几何量**（体积 / 面数 / 边数 / 实体数 / 包围盒 /
文件签名），就是为了防这个。本文收录的是：**几何量不肯动**的那批。

---

## 一、分类

| 类型 | 特征 | 项 |
|---|---|---|
| **A. 建出了空特征** | 特征树里出现特征，体积/面数不变 | `sw_edge_flange` |
| **B. 返回但零几何** | 返回 `True`/对象，元素不变 | `sw_hole_wizard`、`sw_split_body` |
| **C. 恒返回否定** | 稳定返回 `False`/`None` | `sw_sketch_extend`、`sw_dimxpert_autodim` |
| **D. 无 API / 无常量** | 类型库里根本没有对应方法或枚举 | `sw_check_geometry`、`sw_knit_surfaces`、`sw_start/stop_macro_recording`、`sw_hide/show_all_planes`、`sw_hide/show_all_sketches` |
| **E. 缺上下文** | API 存在，但需要前置对象/文档类型 | `sw_add_detail_view`、`sw_add_section_view`、`sw_add_revision_table`、`sw_export_dxf`、`sw_export_flat_pattern`、`sw_fold`、`sw_unfold`、`sw_flow_project`、`sw_add/delete_equation`、`sw_miter_flange` |
| **F. 已知不稳** | 能跑但会卡/判据不立，不进回归 | `sw_add_sketch_dimension`、`sw_show_all_planes` |

---

## 二、逐项证据

### A/B 类：最危险的一类（看着成功）

#### `sw_edge_flange`（边线法兰）

```
edge.Select2(False, 1)                                  # 选中一条边
sk = doc.InsertSketchForEdgeFlange(edge, rad(90), False) # 返回草图特征「草图8」
doc.InsertSheetMetalEdgeFlange(edge, sk, 0, rad(90),     # 返回 CDispatch
                               0.002, 0, 0.0, 0, 0.5, 0.001, 0.001)
```

| 指标 | 调用前 | 调用后 |
|---|---|---|
| 特征 | 4 | **5**（多了 `EdgeFlange`） |
| 体积 | 4800.0 mm³ | **4800.0** |
| 面 / 边 | 6 / 12 | **6 / 12** |

**根因**：`InsertSketchForEdgeFlange` 造出的轮廓草图是**空的**
（`GetSketchSegments()` = 0、`GetSketchPoints()` = 0），
而 `IEdgeFlangeFeatureData` 全部成员里**没有 Length** —— 法兰长度只能来自那条草图。
草图空 → 长度 0 → 零几何。

排除项：`SetBendState(0/1/2/3)` + `EditRebuild3` 无效；特征数据本身是"合法"的
（`GetEdgeCount=1`、`BendAngle=π/2`、`BendRadius=2mm`）；
改 `OffsetType` 直接抛 `RPC_E_SERVERFAULT`。

#### `sw_hole_wizard`（孔向导）

按官方示例 27 参调用（`swWzdHole=2` / `AnsiMetric=1` / `Pan=32` / `M6` / 贯穿）：

| 选择对象 | 返回 | 体积 48000 → |
|---|---|---|
| 顶面 | `None` | **48000** |
| 基准面 | `None` | **48000** |

**结论**：参数齐了也不出几何。等价能力走 `sw_threaded_hole`
（底孔 `FeatureCut4` + 倒角 + 真实螺纹，8/8 门槛通过）。

#### `sw_split_body`（分割实体）

```
doc.Extension.SelectByID2("上视基准面", "PLANE", 0,0,0, True, 0, none_dispatch(), 0)
pre = doc.FeatureManager.PreSplitBody2      # 属性，不是方法！返回 2 个分割体
doc.ClearSelection2(True)                   # 官方示例要求清选择
doc.FeatureManager.PostSplitBody2(pre, True, origins, names, "")   # → None
```

`PreSplitBody2` **能算出 2 个分割体**（说明刀具被正确识别），
但 `PostSplitBody2` 在 6 种封装下全部返回 `None`、实体数恒为 1：

* `ConsumeCut` = `True` / `False`
* `BodiesToMark` = `tuple` / `list` / `VARIANT(VT_ARRAY|VT_VARIANT)` / 单个体
* `Origins`+`SavePaths` = 长度匹配的空值数组 / 类型化 `VT_BSTR` 数组 / 真实存盘路径

补充：传 `VARIANT` 封装的那几处会报 `DISP_E_PARAMNOTOPTIONAL`
（说明这些位置不吃 VARIANT）；`swFm`（132 项）里**没有** split 定义 id，
所以也走不了 `CreateDefinition` 路线（螺纹孔就是靠那条路成功的）。

### C 类：恒返回否定

#### `sw_sketch_extend`（草图延伸）

`SketchExtend(X, Y, Z)` —— 3 个参数是**目标点坐标**，不是"选线段"（这点容易理解错）。

| 选择对象 | 返回 | 线长 |
|---|---|---|
| 线段（10 mm） | `False` | 10 → **10** |
| 端点 | `False` | 10 → **10** |

#### `sw_dimxpert_autodim`（DimXpert 自动尺寸方案）

`AutoDimensionScheme(option)` 返回 `False`、`GetAnnotationCount` 仍 0。
需要先设 `PartType`/`ToleranceType` 或先选要素。读取侧的 `sw_dxp` 是通的（已验证）。

### D 类：类型库里没有

| 项 | 查证结果 |
|---|---|
| `sw_check_geometry` | `sldworks.tlb` 只有 `IModelDoc2.DebugCheckBody` / `DebugCheckIgesGeom`，**没有** `CheckGeometry`；`swcommands.tlb` 只有 `swCommands_Debug_Check_Iges_Geom` |
| `sw_knit_surfaces` | 只有 `IMirrorSolidFeatureData.KnitSurface` / `IPartingSurfaceFeatureData.Knit` 这类**别的特征**的属性，没有独立的缝合接口 |
| `sw_start/stop_macro_recording` | 含 record/macro 的只有 `InsertMacroFeature*` 与 `IJournalManager.WriteJournalToMacro`，都不是"录制" |
| `sw_hide/show_all_planes`、`sw_hide/show_all_sketches` | `swUserPreferenceToggle_e` 里没有基准面/草图开关（实测仅 10 项：`DisplayAxes`/`EntityPoints`/…） |

### E 类：缺上下文

| 项 | 卡点 |
|---|---|
| `sw_add_detail_view` | 详图需要父视图上已存在**详图圆**（detail circle） |
| `sw_add_section_view` | 剖视要在视图上画**剖切线**，不是选基准面；图纸里也没有"前视基准面" |
| `sw_add_revision_table` | 空模板与真实 `.sldrevtbt` 模板都返回 `None` |
| `sw_export_dxf`、`sw_export_flat_pattern` | 零件直接导 DXF 无输出 —— 需要工程图或展开图上下文 |
| `sw_unfold`、`sw_fold` | 能切 `GetBendState` 但几何不变；折叠更要有展开态 |
| `sw_flow_project` | `CreateProject` 返回 `IProject`，但 `GetProjectsCount` 仍 0；整轮求解要先配边界条件/目标/网格 |
| `sw_add/delete_equation` | `IModelDoc2` 没有 `AddEquation`；`IEquationMgr` 需 comtypes 强类型，pywin32 下 `GetEquationMgr` 报找不到成员 |
| `sw_miter_flange` | 同 `edge_flange`：需要可选边集 + 轮廓，且同属"钣金轮廓生成"这条有缺陷的路径 |

---

## 三、共性教训（这部分最值钱）

### 1. 属性 vs 方法（本仓库已踩 5 次）

pywin32 的 late binding 下，有些成员是**属性**，调用会报"找不到成员"或"tuple 不可调用"：

| 成员 | 正确用法 |
|---|---|
| `IFeature.GetDefinition` | **属性** |
| `IFeatureManager.PreSplitBody2` | **属性**（返回 tuple） |
| `IModelDoc2.GetBendState` | **属性** |
| `ISldWorks.GetProcessID` | **属性** |
| `IPartingLineFeatureData.DraftAnalysis` | 方法（但必须先 `AccessSelections`） |

判别法：`isinstance(node, types.MethodType)`；**不要**用 `callable()` ——
pywin32 的 `CDispatch` 本身可调用，会把属性误判成方法。

### 2. `None` 不等于"空 IDispatch"

需要 `IDispatch` 的可选参数，传 Python `None` 会报"类型不匹配"：

* `SelectByID2(..., Callout=none_dispatch(), ...)`
* `InsertCombineFeature(op, MainBody=none_dispatch(), arr)`
* `InsertSheetMetalEdgeFlange(edge, sketchObj, ...)`（第 2 参要**特征对象**，传名字也报错）

### 3. 输出参数要 `VT_BYREF`

`SaveAs4(Name, Version, Options, Errors, Warnings)` 的 `Errors`/`Warnings`：

```python
VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
```

传 `0`/`None` 都报"类型不匹配"。

### 4. 选择标记（mark）不是可有可无

| 操作 | 标记 |
|---|---|
| 镜像**特征** | 特征 **1**、基准面 **2** |
| 镜像**实体** | 实体 **256**、基准面 **2** |
| 移动/复制实体 | 实体 **1** |
| 草图转换实体引用 | 被引用边/面，标记 0 即可 |
| 螺纹 `ThreadFeatureData.Edge` | `edge.Select2(False, 1)` |

### 5. 扩展名与坐标单位

* IGES 只认 **`.igs`**：传 `.iges` 会**静默 0 字节**（`export_iges` 里已归一化）
* `SelectByID2` 的坐标是**米**；`InsertMoveCopyBody2` 的 `TransX/Y/Z` 也是**米**（字面位移）
* `InsertComponent` 是**毫米**（这条曾经把干涉检查搞成"分离的零件也报干涉"）

### 6. 判据必须是几何量

本仓库已验证的 149 项全部遵守：

* 体积变化 / 面数变化 / 边数变化 / 实体数变化 / 包围盒位移
* 文件：存在 + 大小下限 + **头部签名**（`ISO-10303-21`、`%PDF`、`SolidWorks IGES`）
* 计数：草图片段数、特征数（**仅作辅助**，不能单独当判据）

---

## 四、复核触发条件（将来 SW 修好了怎么发现）

以下测试断言的是**否定事实**，一旦 SW 行为改变就会**失败**，提醒重新评估：

| 测试 | 固化的否定结论 |
|---|---|
| `tests/draft_check.py` | 分型线无法用 API 创建；`MoldDraftAnalysis` 恒 False |
| `tests/draft_read_check.py` | 有分型线时可读（正例）；没有时明确拒绝 |
| `tests/flange_probe_check.py` | 边法兰轮廓草图是空的；特征建了但几何不变 |
| `tests/split_extend_check.py` | `PostSplitBody2` 从不产出特征；`SketchExtend` 恒 False |

正确姿势：**不要删掉这些测试**。它们不是"记录 bug"，而是"等你来复核的探测器"。

---

## 五、还没试到底的两条

| 项 | 想法 |
|---|---|
| `sw_unfold` | 之前是在**平板**上试的（无折弯）。现在有 `insert_bends` 造的带 `ProcessBends` 的件，值得重试 |
| `sw_miter_flange` | 与 `edge_flange` 同族，但斜接法兰的轮廓可能由**两条边**决定，未逐一试选择组合 |
