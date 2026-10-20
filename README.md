# swkit — 我自己的 SolidWorks 自动化工具内核

> 不是"又一个 188 工具清单"，而是**带判据的工具内核**：每个宣称可用的能力，都在
> `swkit.registry` 里登记了真实 API、实测证据，以及——同样重要的——**哪些根本用不了、为什么**。

一个仓库，四个入口，同一套能力：

| 入口 | 用法 | 面向 |
|---|---|---|
| Python 库 | `from swkit import SolidWorksApp, pattern_component` | 自己写脚本、做二次开发 |
| CLI | `swkit status` / `swkit pattern-component --kind linear` | 手动跑、批处理、排查 |
| MCP server | `swkit-mcp`（stdio） | 任意 MCP 客户端（Claude / DSH / Editor） |
| Agent skill | `skills/solidworks-automation/SKILL.md` | 让 agent 知道"该怎么用、别踩什么" |

---

## 为什么不是直接 fork 上游

上游 [Solidworks-MCP-Server](https://github.com/Eduardof0nt/Solidworks-MCP-Server) 是很好的起点
（188 个工具、MIT、分组清晰），但实测下来有一批实现**结构上不可能生效**：

- `pattern_component_linear` 调的 `IFeatureManager.LocalLinearComponentPattern`、
  `mirror_component` 调的 `InsertMirrorComponents2` —— **`sldworks.tlb` 里不存在**这两个方法；
- `mirror_component` 另一条路 `IAssemblyDoc.MirrorComponents3` 在 SW2025 文档里明确
  **"Obsolete. Superseded by CreateDefinition/CreateFeature/IMirrorComponentFeatureData"**；
- 组件阵列把**特征**的选择标记（mark=4）用在**组件**上——官方 Remarks 表里组件是 mark=1，
  方向是 mark=2/4，刚好相反。结果就是"调用成功返回 None、选中数恒为 1"。

这些不是"参数没调对"，所以这个仓库的做法是：**保留工具名以便迁移，实现全部按实测配方重写**，
并把结论写进 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md)。上游署名见 [`NOTICE.md`](NOTICE.md)。

---

## 快速开始

```powershell
# 1) 安装（Windows + 已装 SolidWorks）
pip install -e .

# 2) 自检三层：包 / 注册表 / COM
swkit selftest

# 3) 看哪些工具真的能用
swkit registry --implemented

# 4) 对当前打开的装配做组件阵列
swkit pattern-component --kind linear --count 3 --spacing 0.05
swkit mirror-component --plane 前视基准面

# 5) 起 MCP（stdio）
swkit-mcp
```

MCP 客户端注册示例（Claude Desktop / DSH 等同理）：

```json
{
  "mcpServers": {
    "swkit": { "command": "swkit-mcp", "args": [] }
  }
}
```

---

## 能力分层（关键设计）

MCP 与 CLI 都按两层暴露，**绝不把"没验证"包装成"已验证"**：

### Tier A · verified（有判据，可直接交付）

| 能力 | 真实 API | 实测证据 |
|---|---|---|
| `sw_pattern_component_linear` | `IFeatureManager.FeatureLinearPattern5` | 组件 2→4 / 2→5；特征 +3/+4；`IsPatternInstance`×2/×3 |
| `sw_pattern_component_circular` | `IFeatureManager.FeatureCircularPattern5` | 组件 2→4（120°）；`IsPatternInstance`×2 |
| `sw_mirror_component` | `CreateDefinition(116)` + `IMirrorComponentFeatureData` + `CreateFeature` | 特征 `镜向零部件1`；组件 2→4；`IsMirrored`×2 |
| `sw_bounding_box` | `IBody2.GetBodyBox` | 100×60×10 mm，X[-50,50] Y[-30,30] Z[0,10] |
| `sw_shell` | `InsertFeatureShell` | 特征 22→23、**面 7→14** |
| `sw_pattern_feature`（linear/circular） | `FeatureLinearPattern3` / `FeatureCircularPattern3` | 特征 22→23（特征 mark=4、方向 mark=1） |
| `sw_split_line` | `InsertSplitLineSil` / `InsertSplitLineProject` | 特征 22→23 |
| `sw_thicken_surface` | `FeatureBossThicken` | 特征 24→25、`Thicken` 特征=1、曲面 1→0 |
| `sw_offset_surface` | `InsertOffsetSurface` | 曲面 1→2 |
| `sw_screenshot` | `IModelDoc2.SaveBMP` | 2,880,054 B（1200×800） |
| `sw_new_drawing` | `CreateDrawViewFromModelView3` | 视图数 2（中文模板只认 `*前视`） |
| `sw_add_center_mark` | `AddCenterMark(x,False)` | `GetCenterMarks` **0→6** |
| `sw_add_centerline` | `InsertCenterLine()` | `GetCenterLines` **0→6** |
| `sw_add_datum_feature` / `sw_add_gtol` / `sw_add_weld_symbol` | 零参插入 | `GetDatumTagCount` / `GetGTolCount` / `GetWeldSymbolCount` **各 +1** |
| `sw_note` / `sw_add_annotation` | `InsertNote` + `SetPosition2` | 文本读回 + 位置 (0.05, 0.05) 读回 |
| `sw_check_interference` | `InterferenceDetectionManager` | **A/B：重叠=1 处 / 分开=0 处** |
| `sw_fix_component` | `FixComponent()` + `IsFixed` | `IsFixed=True` |
| `sw_show_all_components` | `ShowComponent()` | 全部组件 `IsHidden(False)=False` |
| `sw_explode_assembly` | `AutoExplode`（**属性**，读取即触发） | 爆炸视图数 +1 |
| `sw_sketch_construction` | `ConstructionGeometry` 属性 | True→False 往返成功 |
| `sw_sketch_text` | `InsertSketchText(9 参)` | 字形轮廓线段 0→1 |
| `sw_add_sketch_constraint` | `SketchAddConstraints` | 约束 0→1 **且**端点 Y 0.002→0.000 |
| `sw_activate_display_state` | `ApplyDisplayState` | `ApplyDisplayState("<默认>_显示状态 1")`=True |
| `sw_list_materials` | 解析 `.sldmat`（XML） | 3 库 / 29 分类 / **474 材料**（`AISI 304` 可检索） |
| `sw_sim_*`（7 个） | Simulation `cosworks` | 100 N → 位移 max **0.698424 mm**；1 N → 0.006984 mm（恰好 1/100，线性自洽） |
| `sw_motion_list` / `sw_motion_read` | `IMotionStudyResults` | 速度 0.1 m/s、`IsOutOfDate=False`（结果集索引必须=4） |
| `swdm_*`（4 个） | 私有 DocumentMgr（SQLite 索引） | 275 文件（168 prt / 79 drw / 28 asm）、组件行 2684、视图行 351 |
| `sw_props` / `sw_scan` | 只读属性 + 批量扫描 | 275 文件一轮扫完 |
| `sw_ovba_selftest` / `sw_vba_dump` | VBA 工程解压 | `enable.swp`：737 B→1106 B、2 模块、304 B 源码 |
| `sw_document_info` / `sw_status` / `sw_registry` | — | 元信息，无需判据 |

外加 registry 里 **53 条 verified 配方**（特征 / 草图 / 出图 / 装配 / 仿真 / 元数据），
每条都带 API 名与"用什么数字证明它成了"。

> 清单不虚高的关键：`verified` 只代表**配方已验证**，另有 `implemented` 标记代表
> **本仓库已编码、现在就能经 CLI/MCP 调**。当前 **21 已编码 / 32 待编码**。
> 用 `swkit registry --implemented` 只看能直接用的那批。

### Tier B · api（透传，**unverified**）

`sw_api(op, params)` 直通 `SolidWorksApp` 的约 70 个高层方法（文档、草图、拉伸/旋转/孔、
配合、视图、导出 STEP/STL/PDF、质量属性…）。响应里永远带 `"status": "unverified"`：
能干活，但**尚未逐个复核**，出货前请自己验。

---

## 已知用不了（有依据，别再试）

| 工具 | 依据 |
|---|---|
| `sw_delete_face` | `IBody2.DeleteFaces3`，option=0/1/2/4/8 × flag=T/F 共 10 组全 `(False, False)`，面数不变 |
| `sw_knit_surfaces` | 类型库无 `InsertKnitSurface`（只有别的特征的 `Knit` 属性） |
| `sw_start_macro_recording` / `sw_stop_macro_recording` | 类型库穷举无 `StartRecording`/`StopRecording` |

另有 2 条**不稳**（`sw_add_sketch_dimension` 曾挂起崩溃、`sw_show_all_planes` 判据不立），
不进自动回归。详见 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md)。

---

## 架构

```
src/swkit/
├─ core/         COM 双栈桥接（pywin32 / comtypes 分流）、选择标记常量、错误类型、基类
├─ api/          高层对象 API：SolidWorksApp（文档/草图/特征/配合/出图/导出）
├─ verified/     实测通过的实现，返回值是**证据字典**而不是"调用了"
├─ registry.py   工具状态登记表：verified / unstable / broken + 依据
├─ mcp/server.py MCP 入口（Tier A 精确 + Tier B 透传）
├─ cli/main.py   CLI 入口
└─ diagnostics/  TLB 反射、官方帮助(.chm)检索、能力探测
```

设计约束（都是踩出来的）：

1. **判据用计数，不用返回值**。`CreateAuxiliaryView()`→None、`InsertSplitLineProject()`→0、
   `FeatureBossThicken()`→0 全都成功了。
2. **写进属性的数组必须回读**。comtypes 会把对象数组**静默丢弃**，`CreateFeature` 只还你 None。
3. **先查官方帮助再猜参数**。`sldworksapi.chm` 里有全部官方示例与选择标记表（在 Remarks 里）。

---

## 实测环境

- SolidWorks 2025 SP4.1（`RevisionNumber 33.4.1`），Windows x64
- Python 3.10+，`pywin32` / `comtypes` / `mcp>=1.0`
- 验收脚本：[`tests/live_check.py`](tests/live_check.py)（真机，非单测）

```powershell
python tests/live_check.py     # 真机：建测试装配 → 组件线性阵列 → 镜像 → 证据字典
python tests/part_check.py     # 真机：包围盒/截图/抽壳/特征阵列/分割线/加厚/偏移（8 项）
python tests/sketch_check.py   # 真机：构造线/草图文字/约束/显示状态/材料库（5 项）
python tests/asm_ops_check.py  # 真机：干涉 A/B + 固定/显示/爆炸（4 项）
python tests/drawing_check.py  # 真机：建图/中心标记/中心线/符号×3/注释（7/8，粗糙度判据不可得）
python tests/mcp_smoke.py      # MCP stdio 握手（不起 SolidWorks，验 server 真能起）
```

> `serverInfo.version` 显示的是底层 `mcp` 库版本（FastMCP 构造函数没有 version 参数）；
> 本包版本看 `swkit status` 的 `swkit_version`。

### 环境变量（都可选）

| 变量 | 作用 | 默认 |
|---|---|---|
| `SW_TLB` / `SWCONST_TLB` | 类型库路径 | `D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\*.tlb` |
| `SWKIT_VENDOR` | 额外的 `sys.path`（例如 vendored `comtypes`） | 空 |
| `SWKIT_HOME` | 缓存 / 临时输出目录 | `~/.swkit` |
| `SWKIT_DM_DB` | DocumentMgr 索引库 | 有旧索引则沿用，否则 `~/.swkit/swdm_lite.db` |
| `SWKIT_OUT` | 扫描输出目录 | `~/swkit_out` |
| `SWKIT_CHM` / `SWKIT_CHM_DIR` | 官方帮助 `.chm` 与解包目录 | 安装目录 / `%LOCALAPPDATA%\swkit\chm` |

---

## 许可

MIT。上游署名与商标声明见 [`NOTICE.md`](NOTICE.md)。
SOLIDWORKS® 是 Dassault Systèmes SolidWorks Corporation 的注册商标，本项目与官方无关。
