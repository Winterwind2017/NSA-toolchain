# AutoCAD 后端矩阵（BACKEND MATRIX）

> 同一个能力在三条执行路径上的可用性**不一样**。swkit 只有 COM 一条路，
> acadkit 必须显式声明"这条能力走哪条后端"，否则会出现
> "在无头模式下调了一个只存在于 GUI 的命令"这类错误。

## 一、四条执行路径

| 路径 | 机制 | 需要 AutoCAD | 典型用途 | 致命限制 |
|---|---|---|---|---|
| **com** | ActiveX 晚绑定（`win32com.client.dynamic.Dispatch`） | 完整版、运行中 | 建模/标注/块/表/布尔 | LT 不支持；必须**晚绑定** |
| **lisp** | AutoLISP 脚本（`SendCommand` / `mcp_dispatch.lsp`） | 完整版、运行中 | COM 缺失的能力（`entmake`、`QDIM`、`SECTION`…） | 阻塞式、要等提示符；脚本写法有坑 |
| **headless** | `accoreconsole` + ezdxf | **不需要 GUI** | 批量、文件级、CI | 无交互命令、无 COM |
| **file** | 纯文件（DWG/DXF/MDB/Excel） | 不需要 | 导出、电气数据库、BOM 源 | 只能读写文件，不能驱动 |

补充：**csg** 不是 CAD 后端，是 Python 内自建几何计算（投影引擎、配合公差表）。
它不依赖 AutoCAD，所以判据最硬（纯数学）。

## 二、能力族 × 后端

图例：✅ 实测可用 · ⚠️ 有条件 · ❌ 不可用 · — 不适用

| 能力族 | com | lisp | headless | file | 备注 |
|---|---|---|---|---|---|
| 几何图元 | ✅ | ✅ | ✅ | — | headless 走 ezdxf 直写 |
| 文字 / 多行文字 | ✅ | ✅ | ✅ | — | |
| 标注（线性/对齐/直径/半径/角度/坐标/弧长） | ✅ | ⚠️ | ❌ | — | 直径/坐标/弧长 **只有 com**（`AddDimDiametric`/`AddDimOrdinate`/`AddDimArc`） |
| 尺寸公差 | ✅ | ⚠️ | ❌ | — | 靠 `DIMTOL`/`DIMLIM` 变量 + 标注属性 |
| 形位公差 GD&T | ✅ | ✅ | ❌ | — | com=`AddTolerance`，lisp=`entmake tolerance` |
| 表格 / BOM | ✅ | ❌ | ⚠️ | — | headless 靠 ezdxf 画线模拟，非真 ACDBTABLE |
| 块 + 属性 | ✅ | ✅ | ⚠️ | — | COM 缺 `AddAttributeDefinition`，需 `entmake ATTDEF` 补 |
| 图层 / 线型 / 字体 | ✅ | ✅ | ✅ | — | com 侧**必须晚绑定**，否则 `Color`/`DimScale` 报 AttributeError |
| 标注样式（DimStyle） | ❌ | ✅ | — | — | `DimStyle` 属性不可写，只能 `ActiveDimStyle` + `setvar` |
| 3D 实体建模 | ✅ | ✅ | ❌ | — | headless 无法建 ACIS 实体 |
| 布尔（并/差/交） | ✅ | ✅ | ❌ | — | |
| 剖切（SECTION/SLICE） | ⚠️ | ✅ | ❌ | — | 命令在，COM 封装未见 |
| 投影视图 | ❌ | ❌ | ❌ | — | **官方全缺**；只能 csg 自建 |
| 导出 DWG | ✅ | ✅ | ✅ | — | |
| 导出 DXF | ✅ | ✅ | ✅ | — | `SaveAs(path,65)` 才是真 DXF |
| 导出 PDF | ✅ | ⚠️ | ❌ | — | `-PUBLISH` 两处都阻塞；须显式配布局 |
| 多布局 | ✅ | ✅ | ❌ | — | `Layouts.Add` + `AddPViewport` |
| 视图缩放 | ✅ | ✅ | — | — | |
| 任意 LISP | — | ✅ | ⚠️ | — | `execute_lisp`（GUI）/ accoreconsole `-i` |
| 电气（AE） | ✅ | — | — | ✅ | 数据在 MDB/Excel，图纸靠 COM |
| PLC | ✅ | — | — | ✅ | |
| P&ID | ✅ | ✅ | ❌ | — | 符号库在 CTO library |

## 三、按后端分组的实现策略

### 3.1 com 优先（默认）

适用：建模、标注、块、表、布尔、导出。
**前提**：`profile == <<VANILLA>>`、完整版、`vl-load-com` 可用
（本机实测 `HAS|vlax-get-acad-object|Y`）。

晚绑定是硬要求：

```python
from win32com.client import dynamic
acad = dynamic.Dispatch("AutoCAD.Application")   # ✅
# 不要用 win32com.client.Dispatch（gen_py 包装不完整）
```

### 3.2 lisp 兜底

什么时候必须用 lisp：

* `entmake ATTDEF` / `entmake tolerance`（COM 缺对应方法）
* `ActiveDimStyle` + `setvar`（DimStyle 属性不可写）
* `QDIM`（基线/连续标注的原生做法）
* `SECTION` / `SLICE`、`LAYERSTATE`
* 任何"命令存在但 ActiveX 没有"的能力（实测 51 个命令存在）

脚本写法铁律（都是踩出来的）：

```
① 单次 (open) + 整体包进 (vl-catch-all-apply (function (lambda ( / ) ...)) nil)
   —— 反复 close+reopen 会耗尽句柄，(open) 返回 nil，后面全不执行
② 不要用 (if ... (progn ...)) 包裹后续语句 —— 后面的语句不执行
③ (vla-put-BackgroundPlot app 0) 会抛错中断整个脚本
```

### 3.3 headless

适用：批量生成 DXF/DWG、无需 AutoCAD 的校验、CI。
用 ezdxf 直写，**判据可直接读回**（不需要重开 AutoCAD）。

限制：建不了 ACIS 实体、没有标注关联、表格是画线模拟。

### 3.4 csg（Python 内）

适用：投影三视图、配合公差查表。
优点：判据是纯数学，最容易做 L3/L4；
缺点：只能处理**轴对齐 box/cyl + add/sub** 这一子集（当前实现范围）。

## 四、后端选择规则（给实现用）

```
1. 能在 com 做 → 用 com（最快、可读回）
2. com 没有但命令层有 → 用 lisp，且必须包 vl-catch-all-apply
3. 不需要 AutoCAD → headless（判据最好写）
4. 纯计算 → csg/python
5. 三条都不行 → 标 dead，并写清替代方案（见 registry）
```

**禁止**：在 headless 里调 lisp 命令；在 lisp 里指望 COM 对象属性可写
（`DimScale` 就是反例）。

## 五、环境前置（每次用例都要验）

| 项 | 期望 | 不满足时 |
|---|---|---|
| profile | `<<VANILLA>>` | **拒绝执行**（会污染用户的 ACADE 配置） |
| AutoCAD 版本 | 完整版（`vlax-*` 可用） | com/lisp 全部降级为不可用 |
| 实例数 | 1 个 | 多余实例会导致 COM 连错文档 + 幽灵文档 |
| `%TEMP%\*.sv$` | 不新增 | 强杀残留 → 下次启动弹"图形修复" |
| TRUSTEDPATHS / SECURELOAD | 与用例前一致 | 探针必须**在杀进程前**显式还原 |
