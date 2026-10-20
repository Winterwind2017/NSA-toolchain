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
2. `swkit registry --status verified` —— **只从这张表里挑能力**。
   表里没有的，要么是 `unverified`（可以试，但必须自己补判据），要么是 `broken`（别再试）。
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
