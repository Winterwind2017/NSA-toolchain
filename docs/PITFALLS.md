# PITFALLS — 把 AutoCAD 当 API 用时踩到的坑（全部本机实测）

> 每条都带"现象 / 实测 / 结论"。**判据必须从 AutoCAD 读回**，不要看返回值 ——
> 本页大半条目都是"返回成功但结果不对"。

## 1. COM 代理会"假死"

| 现象 | 实测 | 结论 |
|---|---|---|
| `AttributeError: Add.ModelSpace` | 冷启动后第一次 `Documents.Add()` 拿到的 doc 代理，`doc.ModelSpace` 报"没有这个属性" | 不是 API 不存在，是**代理失效**：重新取 `ActiveDocument`，并做一次 `ModelSpace.Count` 自检 |
| `AttributeError: <unknown>.Open` / `Open.Close` | `Documents.Open` / `doc.Close` 偶发同样报错 | 同上；Close 失败按文档名重找再试 |
| `AttributeError: AutoCAD.Application.Documents` | 刚关完文档就 `clean_quit` 读 `Documents.Count` | 退出前 `com.refresh(app)` 重取一次代理再操作 |
| `com_error: 被呼叫方拒绝接收呼叫`（`RPC_E_CALL_REJECTED`） | 关文档后立刻 `Documents.Add()` 必挂；读 `ModelSpace` 也会 | COM 的忙等待约定：`com.retry()` 等一会儿重试（本项目铺在读回路径与每次取 ModelSpace 上） |

**规矩**：`refresh()` 只换真实 COM 对象（有 `_oleobj_`），离线测试用的假对象
原样返回 —— 否则在装了 pywin32 的机器上跑 pytest 会把用户正开着的 AutoCAD
Quit 掉。

## 2. 出图：`PlotToFile` 返回 True 但文件是 0 字节

默认 `BACKGROUNDPLOT=2`（后台出图），文件要等**文档关闭**才落盘；探针里轮询
15 s 仍是 0 字节。做法：出图前 `SetVariable("BACKGROUNDPLOT", 0)`，出图后
还原并**读回校验**（`export.pdf` 的 `env_restored` 检查就是这条）。

## 3. 布尔：ActiveX `Solid3D.Boolean` 算错

两个 8000 的盒子（重叠 2000）：

| 调用 | 期望 | 实测 |
|---|---|---|
| `box.Boolean(1, other)`（union） | 10000 | **4000** |
| `box.Boolean(2, other)`（subtract） | 6000 | **4000** |
| `box.Boolean(3, other)`（intersect） | 2000 | 报"参数 Operation 无效" |
| `_.UNION`（命令行，按句柄选） | 10000 | **10000** ✅ |

结论：布尔走命令行 + **按句柄精确选择**；SUBTRACT 有两组选择集
（`h1 "" h2 ""`）；命令执行后被合并的实体已删除，**句柄必须在执行前取好**。

## 4. `AddBox` 的 origin 是**中心**，不是角点

由并集体积反推：两个 40 宽的盒子放在 x=500 与 x=520，若 origin 是角点则重叠
20、并集 12000；若是中心则它们的 x 区间是 480–520 / 500–540，重叠 20，并集
同样 12000 —— 这个例子分不出来。用 40 宽 + 20 宽、偏移 20 的例子才分得出来：
角点模型下不重叠（并集 12000），中心模型下重叠 10（并集 10000），**实测
10000**。所以后续几何都按"中心"排。

## 5. 表格第 0 行是合并标题行

往 `ACDBTABLE` 的 (0,1)/(0,2) `SetText`：内存读得到，**落盘重开变空串**
（纯 ASCII 也一样，不是编码问题）。表头放第 1 行；BOM 用 5 行排法
（标题 + 表头 + 2 明细 + 合计），合计判据再核对 5 = 2 + 3。

## 6. 命令会卡在提示符上（`SendCommand` 永不返回）

| 命令 | 现象 | 结论 |
|---|---|---|
| `_-LAYERSTATE\n_Save\n名字\n` | 动过图层表后**永久挂起**（COM 建层 / entmake / SaveAs 之后都一样）；LISP `command`、`vl-cmdf` 也救不了 | 放弃命名图层状态，改属性级快照 |
| `(command "_.UNION" …)` | 双文档下偶发挂起 | 改 `(vl-cmdf "…")`（非交互） |
| `(command "_.SLICE" …)` | 同样 | 改 `(vl-cmdf …)`，并给每例加看门狗 |

看门狗：单例超过 `--case-timeout` 就强杀 acad 并 `os._exit(9)`，现场写
`TIMEOUT.txt`；`progress.txt` 记录到 build/save/reopen/judge 哪一步。

## 7. 属性/方法名与文档不一致

| 对象 | 坑 |
|---|---|
| `LWPOLYLINE` | **没有** `NumberOfVertices`（只有旧 `POLYLINE` 有）；顶点读 `Coordinates` 的坐标对 |
| `MLeader` | `TextString` 赋值不报错、读回空串 → 气泡用圆+线+文字拼 |
| 标注 | `TextPosition` 会被自动避让（传 (30,10) 读回 (30,11.875)）→ 只判"在哪一侧" |
| `AddDimLinear` | **不存在**（本机 `AddDimRotated` 才是线性标注）→ 当负例用 |
| `AddRevolvedSolid` | 任何轮廓都报"输入无效" → 未交付（见 UNSUPPORTED） |
| 3DSOLID | `SolidType` 读会抛异常；`Volume` / `Centroid` 可用 |
| 图层颜色 | `layer.Color` 是 int；有时返回 `AcCmColor` 对象 → 两种都要兼容 |

## 8. 环境变量与 profile

- `CPROFILE` 是**文档级**的：没开文档读不到（`app.GetVariable` 返回 None）。
- 直接启动 `acad.exe` 会落到 `<<ACADE>>`（电气）；必须
  `acad.exe /p "<<VANILLA>>"`。
- `TRUSTEDPATHS` / `SECURELOAD` 是**持久化**变量：为了让 `(load ...)` 能跑而
  改它们，忘还原就污染用户配置（本项目踩过三次）。要跑 LISP 用内联
  `(progn ...)`，不需要信任设置。
- 收尾别用 `Stop-Process -Force`：`%TEMP%\*.sv$` 不清，下次启动弹"图形修复"。
