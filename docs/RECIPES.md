# RECIPES —— 实测通过的配方（照抄即可，别再试别的）

> 环境：SolidWorks 2025 SP4.1（`RevisionNumber 33.4.1`）、Windows x64、Python 3.10+。
> 每条配方后面标了"怎么证明它成了"——**用计数和标志位，不要用返回值**。

---

## 1. 组件线性阵列 / 圆形阵列

**真因**：组件与特征的选择标记**刚好相反**。官方
`IFeatureManager::FeatureLinearPattern4/5` 的 Remarks 表：

| 选择方式 | 选**特征** | 选**组件** |
|---|---|---|
| `SelectByID2` | 方向1=1、方向2=2、要阵列的特征=4 | **要阵列的组件=1**、**方向=2 和 4** |

用 mark=4 去选组件，SolidWorks 当成"方向 2"，方向 1 从未选中 → 必然 no-op。

```python
from swkit.core.com import none_dispatch
from swkit.verified.assembly import pattern_component

# 方向边：必须落在真实几何上 —— 用 GetBox 的 12 条棱中点逐个试
res = pattern_component(asm_doc, kind="linear", count=3, spacing=0.05)
print(res["ok"], res["detail"]["is_pattern_instance"])   # 2
```

内部等价写法（自己写时照这个）：

```python
box = comp.GetBox(False, False)          # 装配坐标，米：[xmin,ymin,zmin,xmax,ymax,zmax]
pt  = (0.5*(box[0]+box[3]), box[4], box[5])
asmw.Extension.SelectByID2("", "EDGE", pt[0], pt[1], pt[2], False, 2, none_dispatch(), 0)
asmw.Extension.SelectByID2("box_hole-1@装配体7", "COMPONENT", 0, 0, 0,
                           True, 1, none_dispatch(), 0)
fmw.FeatureLinearPattern5(3, 0.05, 1, 0.0, False, False,
                          "NULL", "NULL",          # DName：字符串 "NULL"，不是空串
                          False, False, False, False, False, False,
                          True, True, False, False, 0.0, 0.0, False, False)
```

三个必须记住的细节：

1. **组件全名 = `组件名@装配标题(去扩展名)`**；只给 `box_hole-1` 返回 False。
2. `DName1`/`DName2` 传**字符串 `"NULL"`**。
3. 方向边**不能按假定零件坐标**给点：组件有平移就全落空。用 `GetBox` 的棱中点。

**判据**：组件数增加 + `IComponent2.IsPatternInstance` 为 True 的组件数 > 0。
（实测 linear count=3 → 2→4、特征 17→20、实例×2；count=4 → 2→5、17→21、×3；circular 120° → 2→4、×2。）

---

## 2. 镜像组件

**真因**：`IAssemblyDoc.MirrorComponents3` 在 SW2025 文档里标注
**"Obsolete. Superseded by `IFeatureManager::CreateDefinition` / `CreateFeature` /
`IMirrorComponentFeatureData`"** —— 旧方法结构上不可能生效（调 4 组参数全返回 None）。

```python
from swkit.verified.assembly import mirror_components

res = mirror_components(asm_doc, plane_name="前视基准面", mirror_type=2)
print(res["ok"], res["detail"]["feature_name"], res["detail"]["is_mirrored"])
```

等价写法：

```python
dataw = docw.FeatureManager.CreateDefinition(116)      # swFmMirrorComponent
dataw.MirrorPlane = plane                              # IFeature；comtypes 下必须先 QI
dataw.MirrorType  = 2                                  # 2=组件原点 1=质心 0=包围盒中心
dataw.ComponentOrientationsAlignToComponentOrigin = \
    win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, [0]*n)
dataw.ComponentsToInstanceAlignToComponentOrigin  = \
    win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, comps)
dataw.SyncFlexibleSubAssemblies = True
dataw.PreserveZAxis = True
feat = docw.FeatureManager.CreateFeature(dataw)
```

两个坑：

- **`MirrorPlane` 不能直接赋 `FeatureByName()` 返回的通用 `_Dispatch`** →
  `DISP_E_UNKNOWNNAME (-2147352570)`。comtypes 下必须先 `.QueryInterface(sw.IFeature)`。
- **组件数组必须用 pywin32 显式 `VARIANT(VT_ARRAY|VT_DISPATCH, [...])`**；comtypes 收到
  `tuple(POINTER(IComponent2))` 会**静默丢弃**（属性回读为 None，`CreateFeature` 只还 None）。
  调用前务必回读 `len(属性)` 自查。

**判据**：`CreateFeature` 返回特征（名字形如 `镜向零部件1`）+ 组件数增加 +
`IComponent2.IsMirrored` 为 True 的组件数 > 0。

---

## 3. 螺纹孔（底孔 + 口部倒角 + 真实螺纹）

**真因**：孔向导（`HoleWizard4` / `InitializeHole`）**不解析规格表**，几何恒为 Ø50.8；
真正能交付的做法是绕过它，自己画底孔再打螺纹。

```python
# ① 底孔：选面 → 草图 → 圆 → FeatureCut4
fm.FeatureCut4(True, False, False, 0, 0, 0.0102, 0.0,
               False, False, False, False, 0.0, 0.0,
               False, False, False, False, False,
               True, True, True, True, False, 0, 0, False, False)
# ② 口部倒角：找孔口圆边 → InsertFeatureChamfer(4, 1, 距, π/4, 0,0,0,0)
# ③ 真实螺纹：CreateDefinition(87=swFmSweepThread) → ThreadFeatureData
#    edge.Select2(False, 1)   ← 选择标记必须 = 1
#    Type="Metric Tap" / ThreadMethod=0 / EndCondition=0 / Pitch / Size / PitchOverride=True
fm.CreateFeature(thread_data)
```

规格表（M3–M12，底孔直径 mm）：M3×0.5/2.5、M4×0.7/3.3、M5×0.8/4.2、M6×1.0/5.0、
M8×1.25/6.8、M10×1.5/8.5、M12×1.75/10.2。

**判据**：`has_tap_drill_cut` / `has_mouth_chamfer` / `real-thread` 三项全 True，
且实测圆柱直径逐一对应规格表（8/8 通过）。

---

## 4. 截图（`SaveBMP` 替代 `SaveImage`）

`IModelDocExtension::SaveImage` 在这台机器上不可用；可用的是
`IModelDoc2::SaveBMP(path, width, height)` → 实测 1200×800 / 24bit / 2.88 MB，返回 True。

---

## 5. 组件插入（所有装配工具的前提）

```python
# 前提必须全部满足，否则 AddComponent5 返回 None：
#   ① 零件必须先被 OpenDoc 打开（否则 getOpenDocument 解析不到）
#   ② 用 comtypes 强类型，不能用 pywin32 动态分派
#   ③ 8 个入参
asmc = app_ct.ActiveDoc.QueryInterface(sw.IAssemblyDoc)
comp = asmc.AddComponent5(part_path, 0, "", False, "", x, y, z)
```

`AddComponent`（无 5）会返回 True 但**特征树里没有组件**——别拿它当成功。
