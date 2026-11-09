# 人工补充（不随 registry 生成）

> 下面这些是历史调查笔记，内容不来自 registry，因此保留为手工维护。

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

上游另有约 44 个工具（`sw_*`）本仓库**尚未逐个复核**。它们通过
`sw_api(op, params)` 透传可用，但响应恒带 `"status": "unverified"`。
迁移计划见 [`MIGRATION.md`](MIGRATION.md)。

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