# PITFALLS —— 踩过的坑（每条都付过代价）

> 这些不是"注意事项"，是**已经浪费过时间**的具体错误。改代码前先扫一遍。

---

## 1. comtypes 与 pywin32 必须分流

| 场景 | 用哪个 | 不用会怎样 |
|---|---|---|
| 取 VARIANT 数组：`GetComponents`、`GetBodies2`、`GetVisibleEntities2` | **pywin32** | comtypes 抛 `KeyError: 9`（VT_DISPATCH 数组解包失败） |
| 传强类型参数（`IFeature`、`IMathTransform`）、要出参 | **comtypes** | pywin32 动态分派拿不到具体接口 |
| 给属性塞**对象数组** | **pywin32** | 见第 2 条 |

配套：pywin32 的对象不能 `.QueryInterface()`；comtypes 的对象不能直接喂 pywin32 的方法。

## 2. comtypes 会**静默丢弃** VARIANT 数组属性

```python
data.ComponentsToInstanceAlignToComponentOrigin = tuple(comps)   # 不报错，但==没写
len(data.ComponentsToInstanceAlignToComponentOrigin)             # → None / 异常
fm.CreateFeature(data)                                           # → None
```

正确写法：`VARIANT(VT_ARRAY|VT_DISPATCH, list(comps))`（pywin32）。
**规则：写进属性的数组，调用前一律回读长度自查。**

## 3. 通用 `_Dispatch` 赋给 `VT_DISPATCH` 属性 → `DISP_E_UNKNOWNNAME`

`FeatureByName()` 返回的是通用 `_Dispatch`。直接 `data.MirrorPlane = plane` 报
`COMError(-2147352570, '未知名称')`。必须先 `plane.QueryInterface(sw.IFeature)`。

## 4. 组件与特征的选择标记**相反**

选特征：方向1=1、方向2=2、要阵列的特征=**4**。
选组件：要阵列的组件=**1**、方向=**2/4**。
用 mark=4 选组件 → 被当成"方向 2"，方向 1 空 → no-op，且选中数恒为 1。

## 5. 方向边不能按"假定零件坐标"给点

组件插进装配后有平移/旋转，原点 ≠ 零件原点。用
`IComponent2.GetBox(False, False)` 拿装配坐标包围盒，再取 12 条棱中点逐个试。

## 6. 组件全名要带 `@装配标题`

`SelectByID2("box_hole-1", "COMPONENT", ...)` → False；
`SelectByID2("box_hole-1@装配体7", "COMPONENT", ...)` → True。
装配标题取 `GetTitle()` 并**去掉扩展名**（中文版模板常是 `装配体1` 这种没扩展名的名字，
也要按"去掉扩展名"的规则统一处理）。

## 7. `FeatureLinearPattern5` 的 `DName1/DName2` 传字符串 `"NULL"`

不是空串 `""`。官方示例即如此。

## 8. 属性/方法双形态

`FirstFeature`、`GetComponents`、`IsFixed`、`GetInterferenceCount`、`GetFirstView`
在不同绑定/版本下可能一个是属性、一个是方法。统一用：

```python
def val(o, n):
    v = getattr(o, n)
    return v() if callable(v) else v
```

本仓库的 `swkit.core.com.val` 就是它。**别写 `doc.FirstFeature()`**——装配文档下会炸。

## 9. 不要信返回值

`CreateAuxiliaryView()`→None、`InsertSplitLineProject()`→0、`FeatureBossThicken()`→0
全都成功了；反过来 `AddComponent`→True 却没插进组件。
判据一律用**计数 + 语义标志位**：特征数、面数、组件数、`IsPatternInstance`、`IsMirrored`。

## 10. 帮助页末尾的 "Obsolete. Superseded by …" 直接决定路通不通

`IAssemblyDoc.MirrorComponents3` 就是这类：方法存在、参数齐全、调用不报错，
但 SW2025 里**不干活**。查 API 时先看这一行。

## 11. SolidWorks 崩的时候是"假活"

进程还在、`RevisionNumber` 还能读、`Responding=True`，但后续 COM 全报
`-2147417851 服务器出现意外情况` / `-2147352567` / `'NoneType' has no attribute 'GetTypeInfo'`。
桌面会出现 `SLDEXITAPP`（标题"SOLIDWORKS 错误报告"）窗口。

处置：关掉那个窗口 → `CloseAllDocuments(True)` → 单独重跑失败的步骤。
**别急着怀疑自己的代码。**

## 12. 跑批处理/回归前先 `CloseAllDocuments`

脚本常要删/覆盖测试文件；SW 里开着同名文档会锁文件 →
`PermissionError: [WinError 32] 另一个程序正在使用此文件`，整轮中断。

## 13. 宽泛 `except: continue` 会吞掉真错误

本项目被坑过三次（`inspect`/`math` 漏 import、`None` 参与算术）。
写探测循环时至少把异常**记进计数器或日志**，否则"找不到边"可能只是自己代码炸了。
