# 坑清单（AutoCAD COM / 命令行）

> 每条都是本机 AutoCAD 2025（`<<VANILLA>>`）实测。改代码前扫一遍；
> 完整记录（含探针脚本名）在内核仓库 `docs/PITFALLS.md`。

## 一、返回值不可信

| 现象 | 实测 | 修法 |
|---|---|---|
| `PlotToFile` 返回 True | 文件 **0 字节**（`BACKGROUNDPLOT=2`，要等关文档才落盘） | 出图前 `BACKGROUNDPLOT=0`，出图后还原并读回校验；判据查文件头 + 页数 + 每页 ops |
| `Solid3D.Boolean(1, other)` 并集 | 两个 8000 盒子（重叠 2000）算出 **4000**（应 10000） | 走命令行 `_.UNION`，按句柄选择 |
| `Solid3D.Boolean(3, other)` 交集 | 报"参数 Operation 无效" | 同上，`_.INTERSECT` |
| `MLeader.TextString = "1"` | 不报错、读回**空串** | 气泡用 CIRCLE + LINE + TEXT 拼 |
| `AddAttribute` 后重开 | 属性值丢失 | 用 `AddAttribute(Height, Mode, Prompt, InsertionPoint, Tag, Value)` 的正确参数序，并 L4 重开验证 |
| 表格 (0,1) 写入 | 内存读得到、重开变空串（合并标题行） | 表头放第 1 行 |

## 二、命令行会挂死

| 命令 | 现象 | 修法 |
|---|---|---|
| `-LAYERSTATE` + `_Save` | 动过图层表（COM 建层 / entmake / SaveAs 之后）**永久卡在提示符**；`SendCommand`、LISP `command`、`vl-cmdf` 都救不了 | 放弃命名图层状态 → `layer.snapshot`（属性级快照） |
| `(command "_.UNION" …)` | 双文档下偶发挂起 | `(vl-cmdf "…")`（非交互） |
| `DIMLINEAR` 带实体/预选 | 卡在 "Select object…" | 不要用命令行建关联标注（见"别试这些"） |
| 任何命令 | 单例超时 | 看门狗：超时杀 acad + `os._exit(9)`，现场写 `TIMEOUT.txt`；`progress.txt` 记录到 build/save/reopen/judge 哪一步 |

## 三、几何/单位

| 现象 | 实测 | 修法 |
|---|---|---|
| `AddBox` 原点 | 是**中心**，不是角点（并集体积 10000 vs 12000 反推） | 计算包围盒时用 center ± size/2 |
| `AddRevolvedSolid` | 三种轮廓都报"输入无效" | 不用（`solid.revolve` 判死） |
| `Rotate3` | LWPOLYLINE / region 上不存在 | 用 `Rotate(basePoint, angle)` 或旋转后重新取坐标 |
| SLICE 剖面点 | 落在几何边缘时切不开 | 剖面放在几何内部（如中心平面） |
| `AddDimension` 的 `TextPosition` | 传 (30,10) 读回 (30,11.875)（自动避让） | 只判"在哪一侧"，不判相等 |

## 四、环境

| 现象 | 实测 | 修法 |
|---|---|---|
| 直接启动 `acad.exe` | 落到 `<<ACADE>>`（电气） | `acad.exe /p "<<VANILLA>>"` |
| 读 `CPROFILE` | 没开文档返回 None（文档级变量） | 保持一个基线文档再读 |
| 改 `TRUSTEDPATHS`/`SECURELOAD` 跑 `(load …)` | 持久化，忘还原污染配置 | 用内联 `(progn …)`；绝不碰 `SECURELOAD` |
| `Stop-Process -Force` 收尾 | 留 `.sv$`，下次启动弹"图形修复" | `clean_quit`（关文档 → Quit → 等进程消失） |
| `GetActiveObject` 返回早期绑定对象 | 属性名按类型库大小写（`fontFile` ≠ `FontFile`） | 删 `%TEMP%\gen_py` 缓存，恢复晚绑定 |
| `conn.Execute(sql)` 返回 tuple | 晚绑定下是 `(recordset, affected)` | 取 `[0]` |

## 五、出图

| 现象 | 实测 | 修法 |
|---|---|---|
| 没配布局就出图 | 白纸（0 个绘图操作符）但"文件存在" | 显式设设备 `DWG To PDF.pc3`、介质 A3、`PlotType=1`、`CenterPlot` |
| `Plot.SetLayoutsToPlot(["A","B"])` | `E_INVALIDARG` | 传 `VARIANT(VT_ARRAY|VT_BSTR, [...])` |
| 同上 + `PlotToFile` | 调用成功、**文件不存在** | 多页 = 逐布局出单页 + 合并（pypdf） |
| `StartBatchMode(True)` + 上述 | `E_FAIL` | 不要用 batch 模式做多页 |
