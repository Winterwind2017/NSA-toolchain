---
name: solidworks-automation
description: 用 swkit 在本机 SolidWorks 2025 上做零件/装配/工程图自动化与结果校验。当用户要求建零件或装配、插入组件、阵列/镜像组件、打螺纹孔、出图与标注、导出 STEP/STL/PDF，或询问"某个 SolidWorks 工具能不能用/为什么失败"时使用。内含实测通过的 API 配方、必须检查的判据，以及已证伪不可用的功能清单（避免重复试错）。
---

# SolidWorks 自动化（swkit）

## 这个技能解决什么

SolidWorks 的 COM API 有一批**反直觉**的地方：同一个功能有"存在但已废弃"的方法、
选择标记对组件和特征刚好相反、某些属性会被 COM 绑定静默丢弃。结果就是
**调用不报错、也没有效果**。这个技能把这些坑固化成了配方与判据。

## 开工前 30 秒

1. `swkit status` —— 确认连上了、SW 版本、当前文档。
2. `swkit registry --implemented` —— **只用这张表**（本仓库已编码、可直接调）。
   想看全部已验证配方用 `--status verified`（其中 32 条标 `·` 的是配方已验证但尚未编码）。
   表里没有的，要么 `unverified`（可试，但必须自己补判据），要么 `broken`（别再试）。
3. 如果要做装配：确认零件已 `OpenDoc` 打开、用 comtypes 的 `AddComponent5`（8 参）插组件。

## 铁律（违反必踩坑）

| 铁律 | 原因 |
|---|---|
| **判据用计数/标志位，不用返回值** | `CreateAuxiliaryView()`→None、`InsertSplitLineProject()`→0 都成功了；`AddComponent`→True 却什么都没插 |
| **写进属性的数组，先回读长度** | comtypes 会把 `tuple(POINTER)` **静默丢弃**，`CreateFeature` 只还 None |
| **组件阵列：组件 mark=1、方向 mark=2/4** | 与"特征阵列"（特征=4、方向=1/2）**相反**；用反了必然 no-op |
| **镜像用 `CreateDefinition(116)`+`CreateFeature`** | `MirrorComponents3` 在 SW2025 已 Obsolete，调了也不干活 |
| **`ClearSelection2` 在 `IModelDoc2` 上** | 不在 `IModelDocExtension` 上 |
| **`IModelDoc2` 不能直接 QI 成 `IFeatureManager`** | 要用 `md.FeatureManager` 再 QI |
| **跑批处理前 `CloseAllDocuments(True)`** | 否则测试文件被占用 → `WinError 32` 整轮中断 |
| **COM 报 `-2147417851 服务器出现意外情况`** | 大概率是 SW 崩了（"假活"）；关掉 `SLDEXITAPP` 错误报告窗口再重试 |

## 典型任务怎么做

### 组件线性/圆形阵列

```python
from swkit.verified.assembly import pattern_component
res = pattern_component(asm_doc, kind="linear", count=3, spacing=0.05)   # spacing 单位米
# 成功判据：res["ok"]，也就是 组件数增加 + IsPatternInstance>0
```

要点：方向边必须用 `IComponent2.GetBox(False,False)` 拿**装配坐标**包围盒再取棱中点；
组件全名是 `组件名@装配标题(去扩展名)`；`DName` 传字符串 `"NULL"`。

### 草图实体（verified，输入 mm）

```python
from swkit.verified import sketch_ops as so
so.create_sketch(doc, "前视基准面")     # 中文版必须用本地化面名
so.line(doc, 0, 0, 50, 0)              # 判据：草图线段 0→1
so.rectangle(doc, 0, 0, 40, 25)        # 0→4
so.circle(doc, 10, 10, 8); so.arc(doc, 0, 0, 15, 0, 90)
so.polygon(doc, 0, 0, 6, 15)          # 6 边形 → 0→7
so.spline(doc, [[0,0],[15,20],[35,10]]) # 必须传 COM 数组
so.exit_sketch(doc)
```

要点：**判据统一是活动草图的线段数**；`CreateSpline(list)` 在 pywin32 下会拿到空成员，
要用 `CreateSpline2` + `VT_ARRAY|VT_R8`；`edit_sketch` 用 `EditSketch()`，
`MenuCommand(2026)` 在本机不可用。

### 出图（verified）

```python
from swkit.verified import drawing
drawing.new_drawing(part, view="front")      # 中文模板只认 *前视，*Front 返回 None
view = drawing.first_model_view(dwg)
drawing.center_mark(dwg); drawing.centerline(dwg)
drawing.symbol(dwg, "gtol")                  # datum / gtol / weld，判据是各自计数 +1
drawing.surface_finish(dwg)                  # 先 ActivateView，判据 GetSFSymbols 0→1
drawing.note(dwg, "技术要求…"); drawing.drawing_dimension(dwg)
drawing.hole_table(dwg)                      # 必须先 ActivateView
drawing.broken_view(view)                    # 判据 GetBreakLines，不是视图数
drawing.aux_view(dwg); drawing.section_view(part_doc, "前视基准面")
drawing.balloon(dwg)   # 需装配图：先 InsertBomTable2(BomType=1) 再选中视图 AutoBalloon2
```

要点：出图类 API 的返回值几乎都不可信，判据一律用**对应集合的计数**
（`GetCenterMarks` / `GetCenterLines` / `GetDatumTagCount` / `GetGTolCount` /
`GetWeldSymbolCount` / `GetSFSymbols` / `GetDisplayDimensions` / `GetBreakLines`）。
**`None` 常常是"0 个"，不是"没有判据"**——先激活视图/换条件重测再下结论。

### 装配检查与整理（verified）

```python
from swkit.verified import asm_ops
asm_ops.check_interference(doc)      # A/B：重叠=1 处 / 分开=0 处；count=0 也算成功
asm_ops.fix_component(doc)           # IsFixed=True
asm_ops.show_all_components(doc)     # 全部 IsHidden(False)=False
asm_ops.explode_assembly(doc)        # 爆炸视图数 +1（AutoExplode 是属性，读取即触发）
```

要点：干涉数为 0 是**正常结果**，不是失败；`IInterference` 要用 comtypes QI 才拿得到成员；
`IBody2.GetMassProperties` **必须传密度**。

### 镜像组件

```python
from swkit.verified.assembly import mirror_components
res = mirror_components(asm_doc, plane_name="前视基准面", mirror_type=2)
# 成功判据：特征创建 + 组件数增加 + IsMirrored>0
```

### 想用表里没有的能力

```python
sw_api("extrude", {"depth": 0.02})     # 透传 SolidWorksApp；响应带 status="unverified"
```

必须自己补一个判据（特征数/面数/体积），不能只看返回值。

### 零件 / 特征（verified）

```python
from swkit.verified import part
part.bounding_box(doc)                      # 100×60×10 mm，X[-50,50] Y[-30,30] Z[0,10]
part.screenshot(doc, r"...\shot.bmp")       # 2.88 MB @1200×800
part.shell(doc, thickness=0.002)            # 判据：面 7→14
part.split_line(doc)                        # 判据：特征 22→23（先零参 InsertSplitLineSil）
part.thicken_surface(doc, 0.002)            # 需要曲面件；判据：出现 Thicken 特征
part.offset_surface(doc, 0.002)             # 判据：曲面 1→2
part.pattern_feature(doc, kind="linear", count=3, spacing=0.02)   # 特征 22→23
```

要点：**特征阵列与组件阵列的标记相反**——特征 mark=4、方向 mark=1；
抽壳的可靠判据是"面数翻倍"而不是返回值（`InsertFeatureShell` 返回 0 也算成功）；
选面用 `IFace2.Select2`，别按坐标 `SelectByID2("", "FACE", …)`。

### 仿真（静力）

```python
from swkit.study import sim
sim.status(open_path=r"...\part.SLDPRT")          # 先看文档/材质/加载项/研究
sim.faces(open_path=..., limit=20)                 # 挑约束面与受力面（索引+坐标）
res = sim.solve(restraint_face=0, force_face=1, force_n=100, material="AISI 304")
# 约 13–15 分钟；位移可信，应力要求同会话读到，否则 stress_available=False
```

要点：100 N 的位移应是 1 N 的 100 倍（线性自洽）；**固定端锐边是应力奇异**，读到
1497 MPa 那是伪值；网格别低于 `size=0.02 / tol=0.002`（会吃满 16 GB）。

### 运动

```python
from swkit.study import motion
motion.list_studies(open_path=asm)
res = motion.read(open_path=asm, samples=11)       # 位移/速度/加速度
```

要点：结果集索引必须 **4**（1/2 是空壳，值恒 0）；位移**不能**用 `GetCMPosition`。

### 元数据（不打开 SolidWorks 也能查索引）

```python
from swkit.meta import docs, props, vba
docs.stats()                       # 275 文件 / 2684 组件行 / 351 视图行
docs.query(prop="外形尺寸", ext="sldprt")
props.props(r"...\part.SLDPRT")    # 单文件自定义属性（含中文名）
vba.dump(r"...\macro.swp")         # 读内嵌 VBA 源码（审计用）
```

要点：`docs.query` **没有全文检索**（只有 `--prop/--dir/--ext`）；
`vba.build()` 会覆盖目标 `.swp`，只能指向副本。

## 需要细节时读这些

- `docs/RECIPES.md` —— 五条完整配方（组件阵列、镜像、螺纹孔、截图、插组件），带等价代码
- `docs/PITFALLS.md` —— 13 条踩坑记录，改代码前扫一遍
- `docs/UNSUPPORTED.md` —— 4 条已证伪 + 2 条不稳；**别重复试这些**
- `references/checklists.md` —— 装配类任务的检查清单（事前/事中/验收）

## 交付前的自检三问

1. **数字变了吗？** 特征数/面数/组件数/符号数，至少一个要有可复现的前后对比。
2. **语义标志位对吗？** 阵列实例看 `IsPatternInstance`，镜像看 `IsMirrored`，
   螺纹看 `ThreadFeatureData` 的 Type/Pitch/Size。
3. **负面对照做过吗？** 把关键参数（标记、方向、类型）换成已知错误值，应该失败。
   不能失败的判据，通常也证明不了成功。
