# UNSUPPORTED —— 用不了的东西，以及为什么

> 这个文件的存在意义：**避免下一轮再去试同一件事**。
> 每条都写了"试过什么、结果是什么、为什么判定不行"。

判定口径：

- `broken` —— 有明确证伪依据（类型库无该方法 / 参数横扫全失败）
- `unstable` —— 曾成功，但会挂起/崩溃，或不具备可构造的判据

---

## broken（4 条）

### `sw_delete_face`

- 尝试：`IBody2.DeleteFaces3(faces, option, flag)`，`option ∈ {0,1,2,4,8}` × `flag ∈ {True,False}`
  = **10 组全试**
- 结果：全部返回 `(False, False)`，面数不变
- 另试：改用 `VARIANT(VT_ARRAY|VT_DISPATCH)` 传数组 —— 同样无效
- 结论：**不可用**。不要再换 option 组合去试。

### `sw_knit_surfaces`

- 尝试：穷举 `sldworks.tlb` 里含 `knit` 的成员
- 结果：只有 `IMirrorSolidFeatureData.KnitSurface`、`IPartingSurfaceFeatureData.Knit`
  —— 都是**别的特征的属性**，不是"缝合曲面"这个功能
- 注意：上游工具名是复数 `sw_knit_surfaces`，**没有**单数 `sw_knit_surface`
- 结论：**类型库无该 API**

### `sw_start_macro_recording` / `sw_stop_macro_recording`

- 尝试：穷举类型库里含 `record` / `macro` 的成员
- 结果：只有 `InsertMacroFeature*`（宏特征）、`IJournalManager.WriteJournalToMacro`、
  `RecordCOMCall` 等；**没有 Start/StopRecording**
- 结论：**类型库无该 API**。录制宏只能在 UI 里点。

---

## unstable（2 条，不进自动回归）

### `sw_add_sketch_dimension`

- `AddAlongXDimension` + `mark=1`：round 17 成功（0.01→0.03）
- 但 round 32 **挂起并崩溃过一次**
- 处置：保留实现，但调用方必须自己加超时保护；**不要放进无人值守批处理**

### `sw_show_all_planes`

- `UnblankRefGeom` 存在且可调用
- 但 `IFeature.Visible` 不反映图形区的实际可见性 → **构造不出"隐藏态"做 A/B**
- 处置：判据未立，不宣称已修

---

## 上游实现里"根本不存在的方法"

这些是 [Solidworks-MCP-Server](https://github.com/Eduardof0nt/Solidworks-MCP-Server)
（MIT，作者 Eduardo Font Cruz）里写错的地方，本仓库已按实测配方重写：

| 上游调用 | 事实 | 本仓库做法 |
|---|---|---|
| `IFeatureManager.LocalLinearComponentPattern` | `sldworks.tlb` 里**不存在** | `FeatureLinearPattern5` + 组件 mark=1 / 方向 mark=2 |
| `IFeatureManager.LocalCircularComponentPattern` | 同上 | `FeatureCircularPattern5` + 同样标记 |
| `IFeatureManager.InsertMirrorComponents2` | 同上 | `CreateDefinition(116)` + `IMirrorComponentFeatureData` + `CreateFeature` |
| `IAssemblyDoc.MirrorComponents3` | 存在，但 SW2025 文档标注 **Obsolete**，实测 no-op | 同上 |

---

## 还没复核的工具

上游另有约 80 个工具（`sw_*`）本仓库**尚未逐个复核**。它们通过
`sw_api(op, params)` 透传可用，但响应恒带 `"status": "unverified"`。
迁移计划见 [`MIGRATION.md`](MIGRATION.md)。

---

## unverified（2 条，能调但没打通）

### `sw_dxp`（DimXpert）

- 能读方案名与标注数量（`action=info`）
- 但 `autodim=True` 会**运行自动尺寸方案并保存文件** —— 破坏性，本仓库默认关闭
- 未做"自动尺寸后几何是否满足标注"的判据，故不标 verified

### `sw_flow_check`（Flow Simulation）

- 加载项自检与建工程可调用
- **未跑通求解**，所以不能算打通
---

---

## 勘误：`sw_add_surface_finish` 曾被误降级（已恢复 verified）

2026-10-20 我先把它从 verified 降到 unverified，理由是"插入只返回 True、IView 没有
粗糙度 getter"。**这个结论是错的**，错在测量条件：

| 条件 | `GetSFSymbols` 返回 | 我的误读 |
|---|---|---|
| 视图**未激活** | `None` | 当成"没有这个 getter"→ 判据不可得 |
| 视图**已激活**（`ActivateView`） | 插入前 0、插入后 1 | 真正可计数 |

所以正确做法是：**先 `ActivateView` 再插入，用 `GetSFSymbols` 的 0→1 做判据**。
代码已按此修正（`None` 一律当 0），并恢复 verified。

教训：**"取不到数"和"没有判据"是两件事**。遇到 `None` 要先换条件重测（激活视图、换视图类型、
换选择标记），再决定降级。这条比任何一条 API 坑都值钱。