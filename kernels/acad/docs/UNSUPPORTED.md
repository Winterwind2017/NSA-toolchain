# 用不了的能力（按"卡在哪里"分类）

> 本文件由 `python tools/gen_unsupported.py` 从 `docs/registry.yaml` 生成。
> **不要手改**：改 registry 的 `status`/`judge`/`evidence`，再重新生成。

这个仓库的原则：**说不清判据的能力不许标 verified**。用不了的也写清楚——
是"本机没有官方路径"，还是"依赖外部资产"，还是"能跑但结果不可信"。


## dead（本机没有可用的官方路径）

| 能力 | 族 | 卡在哪里 / 替代方案 | 证据 |
|---|---|---|---|
| `block.edit_inplace` | block | BEDIT/ATTSYNC/ATTREDEF/BATTMAN 均不存在。替代：重定义块 + 重插全部引用；.NET 通道已打通，BlockEditor 待实现（插件里 ACADKITEDITBLOCK 先占位） | matrix #2.2 |
| `constraint.geometric` | constraint | **无替代**：完整版 AutoCAD 也无 GEOMCONSTRAINT/DIMCONSTRAINT/PARAMETERS；参数化只能在 Python 侧做参数驱动重建 | matrix #29 / #3.2 |
| `dim.associative` | dim | **外部进程不可达**：ActiveX AddDimRotated 建的标注天然非关联（IAcadDimension 无 assoc API）；DIMLINEAR 点选/选对象/预选、DIMREASSOCIATE、OSMODE+REGEN 六种输入都在提示符卡死或 Measurement 不跟随。替代=.NET 通道已打通（dotnet/AcadKit.Plugin，安装目录+注册表加载）用 DimensionAssociation；当前仍用「重建式更新」=dim.update | P1 探针 2026-10-21（_scratch/probe_assoc*.py） |
| `interfere` | boolean | INTERFERE 命令不存在。替代：布尔求交（INTERSECT）后看结果体积，>0 即干涉 | matrix #2.2 |
| `view.projection_builtin` | view | **官方命令全缺**：SOLVIEW/SOLDRAW/SOLPROF/FLATSHOT/-FLATSHOT/EXPORTLAYOUT 均不存在；替代=自建 CSG 投影（见 projection.orthographic） | matrix #2.2 / #3.2 |

## external（不属于本内核的交付范围）

| 能力 | 族 | 为什么 | 证据 |
|---|---|---|---|
| — | — | 当前没有 external：原来的 4 条（Electrical 库 / PLC / P&ID / 投影）已在 2026-10-21 的接口挖掘里转成 verified，见 `CAPABILITIES.md` | — |

## 看着能用、其实不能用的坑（实测）

这些不是 registry 里的某条能力，而是做能力时踩到的"调用成功但结果不对"，
写在这里防止后来者再信返回值：

| 现象 | 实测 | 结论 |
|---|---|---|
| `Solid3D.Boolean(1, other)` 并集 | 两个 8000 的盒子（重叠 2000）算出 **4000**；`Boolean(3, …)` 报"参数 Operation 无效" | ActiveX 布尔不可用，改走命令行 `_.UNION/SUBTRACT/INTERSECT`（按句柄选择） |
| `Plot.PlotToFile` | 返回 True，文件 **0 字节**（默认 `BACKGROUNDPLOT=2`，要等文档关闭才落盘） | 出图前临时置 `BACKGROUNDPLOT=0`，用完还原并读回校验 |
| `MLeader.TextString` | 赋值不报错、读回**空串** | 序号气泡改用圆 + 引线 + 文字拼 |
| `-LAYERSTATE` | 只要动过图层表（COM 建层 / entmake / SaveAs 之后），Save **永久卡在命令提示符**；`SendCommand`、LISP `command`、`vl-cmdf` 全试过 | **已用 .NET 通道解决**：`layer.state` 走 `LayerStateManager`（进程内），见 `dotnet/`。ActiveX 侧仍不可用，故保留本条 |
| `(command "…")` in `SendCommand` | 双文档（基线 + 用例）下偶发挂起 | 改用 `(vl-cmdf "…")`（非交互），并给每例加看门狗 |
| `_.NETLOAD`（命令行 / `vl-cmdf`） | **弹模态文件对话框，SendCommand 永久阻塞**（FILEDIA=0 无效） | 不要用 NETLOAD。改注册表 `LOADCTRLS=2` + 把 DLL 放进 **AutoCAD 安装目录**（`SECURELOAD=1` 会拒绝未信任路径） |
| Autoloader bundle | bundle 放进 `%APPDATA%\Autodesk\ApplicationPlugins\` 后命令仍"未知命令" | 同上，走安装目录 + 注册表；`tools/netload.py --deploy` 已封装 |
| `AddRevolvedSolid` | XY 矩形 / 圆 / 3D 多段线三种轮廓都报"输入无效"；命令行 `_.REVOLVE` 也没生成实体 | **已用 .NET 通道解决**：`solid.revolve` 走进程内 `Solid3d.CreateRevolvedSolid`，实测体积误差 0.0；ActiveX 侧仍不可用 |
| `LWPOLYLINE.NumberOfVertices` | 只有旧 `POLYLINE` 有这个属性 | 顶点用 `Coordinates` 的坐标对读 |
| 标注 `TextPosition` | 传 (30,10) 读回 (30,11.875)（自动避让） | 只判"文字在尺寸线哪一侧"，不判相等 |
| `ACDBTABLE` 第 0 行 | 是**合并标题行**，往它的第 1..n 列 `SetText`：内存读得到、落盘重开变空串（ASCII 也一样） | 表头放第 1 行，BOM 用 5 行排法 |


## 复核触发条件

上面这些结论都带"本机 + 版本"的前提（AutoCAD 2025 / R25.0 / `<<VANILLA>>`）。
出现以下情况时要重新测，不要直接沿用：

1. 换 AutoCAD 版本（R26+）或换机器；
2. Autodesk 更新了 ActiveX 类型库（`acdbmgd`/`acad` 的 COM 接口）；
3. 判据在某台机器上突然失败，而代码没改——先怀疑环境，再怀疑能力。

复核方法：`python tests/live_judges.py --only <族>`，看 `_scratch/.../progress.txt`
与 `results.json` 的 `detail/raw`。
