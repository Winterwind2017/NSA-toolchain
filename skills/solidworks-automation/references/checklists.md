# 装配类任务检查清单

> 装配是这套工具里最容易"看着成功、其实没动"的地方。按顺序过。

## 事前

- [ ] `swkit status` 连上了，且 `open_documents` 是你预期的数量
- [ ] 要插入的**零件已用 `OpenDoc` 打开**（`AddComponent5` 的前置条件，否则返回 None）
- [ ] 插组件用 **comtypes 强类型** + **8 个入参**：
      `asmc.AddComponent5(path, 0, "", False, "", x, y, z)`
- [ ] 插完**核对组件数**（`len(GetComponents(False))`）。别信 `AddComponent` 的 True。
- [ ] 打算跑批处理的话，先 `CloseAllDocuments(True)`

## 事中（阵列/镜像）

- [ ] 组件阵列：**组件 mark=1、方向 mark=2**
      （特征阵列才是 特征=4、方向=1/2，别混）
- [ ] 方向参考用 `IComponent2.GetBox(False, False)` 的**装配坐标**棱中点，
      不要用零件坐标假想值
- [ ] 组件全名 `名字@装配标题`（标题去扩展名）
- [ ] `FeatureLinearPattern5` 的 `DName1/DName2` = 字符串 `"NULL"`
- [ ] 镜像：`CreateDefinition(116)` → 设 `MirrorPlane`（comtypes 下先 QI 成 `IFeature`）
      → 组件数组用 `VARIANT(VT_ARRAY|VT_DISPATCH, [...])`
      → **回读 `len(属性)` == 组件数** → `CreateFeature`
- [ ] 出现 `SLDEXITAPP`/错误报告窗口 = SW 崩了；关窗口 + `CloseAllDocuments` 后重试

## 验收

- [ ] 组件数**确实增加**（记下具体 `before → after`）
- [ ] `IsPatternInstance` / `IsMirrored` 为 True 的组件数 **> 0**
- [ ] 特征树里出现对应特征（如 `镜向零部件1`），记下特征名
- [ ] 负面对照（可选但强烈建议）：把 mark 换成旧值 4/1，应当 **no-op**
- [ ] 把 `before/after/标志位/特征名` 一起写进交付说明，而不是只说"已生成"
