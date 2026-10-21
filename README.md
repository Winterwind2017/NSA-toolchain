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
| `sw_add_auxiliary_view` | `CreateAuxiliaryView()`（零参） | 视图数 **2→3** |
| `sw_create_section_view` | `CreateSectionViewData`+`CreateSectionView` | 返回 True 并自动复位 |
| `sw_add_broken_view` | `IView.InsertBreak2(5 参)` | `GetBreakLines` **+1**（不新增视图） |
| `sw_add_drawing_dimension` | `AddDimension2(x,y,0)` | `GetDisplayDimensions` **0→1** |
| `sw_add_hole_table` | `InsertHoleTable2`（须先 `ActivateView`） | 表格数 **0→1** |
| `sw_add_surface_finish` | `InsertSurfaceFinishSymbol2` | 激活视图后 `GetSFSymbols` **0→1** |
| `sw_add_balloon` | `InsertBomTable2` + `AutoBalloon2` | 装配图 2 组件 → **2 个气球 / 2 条注释** |
| `sw_add_center_mark` | `AddCenterMark(x,False)` | `GetCenterMarks` **0→6** |
| `sw_add_centerline` | `InsertCenterLine()` | `GetCenterLines` **0→6** |
| `sw_add_datum_feature` / `sw_add_gtol` / `sw_add_weld_symbol` | 零参插入 | `GetDatumTagCount` / `GetGTolCount` / `GetWeldSymbolCount` **各 +1** |
| `sw_note` / `sw_add_annotation` | `InsertNote` + `SetPosition2` | 文本读回 + 位置 (0.05, 0.05) 读回 |
| `sw_move_component` | `Transform2`（变换拷贝法） | Δ=[**0.05**, 0, 0]，临时件已删、组件数不变 |
| `sw_extrude` | `FeatureExtrusion3` | 40×25×20 → 体积 **20000.0 mm³**（手算一致） |
| `sw_connect` / `sw_create_part` / `sw_create_reference_plane` | `NewDocument`/`InsertRefPlane` | 版本 33.4.1；`GetType==1`；RefPlane **3→4** |
| `sw_select_entity` / `sw_clear_selection` | `SelectByID2`/`ClearSelection2` | 选择集 **1 → 0** |
| `sw_capture_screenshot` / `sw_delete_feature` | `SaveAs(PNG)`/`DeleteSelection2` | PNG 魔数 **125 KB**；特征数 **-1** |
| `sw_planar_surface` | `InsertPlanarRefSurface`（属性） | 闭合草图 → 曲面 **0→1** |
| `sw_revolved_surface` | `InsertRevolvedRefSurface`（4 参） | 矩形+中心线 → 曲面 **0→1** |
| `sw_cut_extrude` | `FeatureCut4`（27 参） | 两处 Ø10 通孔：48000→**46115.044**（每孔 −942.478） |
| `sw_check_interference` | `InterferenceDetectionManager` | 分开 120mm→**0**；重叠 20mm→**1**；重合→**1** |
| `sw_insert_bends` | `IPartDoc.InsertBends`（6 参） | L 形实体 → **SheetMetal+ProcessBends+FlatPattern**，bendState 0→3 |
| `sw_dxp` | `swdimxpert.tlb`（独立 TLB） | `create=False`→无 schema；`create=True`→schema**模式2**、要素 0、标注 0 |
| `sw_chamfer` | `InsertFeatureChamfer(8 参)` | 4 边倒角 5mm：体积 48000→**46616.667**、面 6→**10**、边 12→**20** |
| `sw_fillet` | `FeatureFillet3`（高层 14 参） | 4 边圆角 r5：体积 48000→**47382.87**、面 6→**10**、边 12→**20** |
| `sw_flow_check` | `EFDApiSrv` + `EFDApi.tlb` | 版本 **Flow Simulation 2025 SP3.0 Build 6784**、静默 True、工程数 0、CAD 文档对象可取 |
| `sw_analyze_draft` | `IPartingLineFeatureData` | 分型线夹具：正拔模 **1**、负拔模 **1**、无拔模 **4**、跨面 **0**，合计 6 = 实体面数 |
| `sw_mirror_feature` | `InsertMirrorFeature2`（标记 1/2） | 20000→**40000**（比 2.0），特征「镜向1」 |
| `sw_revolve` | `IModelDoc.FeatureRevolve2`（5 参） | 25132.741 mm³ = πR²h；360°:180° = **2.0000** |
| `sw_sketch_circular_pattern` | `CreateCircularSketchStepAndRepeat`（9 参） | 线段 1→**4**、总长 ×4 |
| `sw_sketch_convert_entities` | `SketchUseEdge3`（2 参） | 选 25mm 边 → 片段 0→**1**、总长 0→**25.0** |
| `sw_extruded_surface` | `FeatureExtruRefSurface3`（22 参） | 闭合草图 → 曲面 **0→1** |
| `sw_sketch_offset` / `sw_sketch_linear_pattern` | `SketchOffset2`(6 参) / `CreateLinearSketchStepAndRepeat`(12 参) | 偏移 4→**8** 段；阵列 1→**3** 份（长度 ×3） |
| `sw_scale_body` | `InsertScale`（5 参） | 选中实体后 40×25×20 → **80×50×40** |
| `sw_delete_body` | `InsertDeleteBody` | 实体数 **2→1** |
| `sw_sketch_trim` | `SketchTrim`（4 参） | 矩形+伸出线：总长 **200→190 mm** |
| `sw_sketch_fillet` / `sw_sketch_chamfer` | `CreateFillet`/`CreateChamfer` | 线段 **4→5**、总长 130→**127.854 / 127.071** |
| `sw_start_3d_sketch` | `Insert3DSketch` | 活动草图存在且 **Is3D=True** |
| `sw_get_equations` / `sw_list_global_variables` | `IEquationMgr.GetCount/Equation/Value` | 空件 0 条；写入后 1 条（`"myvar" = 5.0`） |
| `sw_set_global_variable` | `IEquationMgr.Add` | 计数 **0→1**，`Value` 读回 **5.0** |
| `sw_create_reference_axis` | `InsertAxis2` | 两基准面 → `RefAxis` **0→1** |
| `sw_zoom_to_fit` / `sw_set_view_orientation` | `ViewZoomtofit2`/`ShowNamedView2` | Scale2 **4.4976**；定向矩阵 **0.884→0.707** |
| `sw_measure_distance` | `IModelDocExtension.CreateMeasure` | 前后面距离 **20.0 mm**（期望 20） |
| `sw_open_document` / `sw_close_document` / `sw_close_all` | `OpenDoc`/`CloseDoc`/`CloseAllDocuments` | 文档数 **0→1、2→1、→0** |
| `sw_save_as_copy` | `SaveAs2`（4 参） | 副本存在且**原路径不变** |
| `sw_list_configurations` / `add_configuration` / `activate_configuration` | `AddConfiguration3`/`ShowConfiguration2` | 配置 **1→2**，激活名读回一致 |
| `sw_get_referenced_documents` | `GetDependencies`（2 参） | 图纸依赖 **2** 项（含 box_hole.SLDPRT） |
| `sw_base_flange` | `InsertSheetMetalBaseFlange`（9 参） | 特征 19→22，出现 **SheetMetal + SMBaseFlange + FlatPattern** |
| `sw_get_flat_pattern_info` | `IFeature(FlatPattern)` | FlatPattern 存在，`GetBendState=1` |
| `sw_hem` | `InsertSheetMetalHem`（8 参） | 特征 22→23 |
| `sw_view_rotate` | `DrawingViewRotate` | `IView.Angle` **0°→15°** |
| `sw_export_drawing_pdf` / `sw_export_drawing_dwg` | `SaveAs` | **%PDF-1.4** 109 KB / **AC1015** 36 KB |
| `sw_export_step` / `sw_export_stl` / `sw_export_file`(PDF) / `sw_save_document` | `SaveAs` | 签名 **ISO-10303-21** / `stlbn` / **%PDF-1.4** / 65 KB 落盘 |
| `sw_create_assembly` | `NewDocument(.asmdot)` | `GetType==2` |
| `sw_insert_component` | `AddComponent5`（8 参） | 组件 **0→1→2**（零件需先打开，插入前切回装配） |
| `sw_get_assembly_tree` | `GetComponents` + 状态位 | 2 个组件，固定/抑制/隐藏全部可读 |
| `sw_suppress_component` | `SetComponentSuppression` | `IsSuppressed` **False→True→False** |
| `sw_hide_component` | `HideComponent/ShowComponent` | `IsHidden` **False→True→False** |
| `sw_replace_component` | `ReplaceComponents2`（5 参） | 路径 **box_hole → box_off** |
| `sw_suppress_feature` / `sw_unsuppress_feature` | `EditSuppress2/EditUnsuppress2` | `IsSuppressed` False→True→False |
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
> **本仓库已编码、现在就能经 CLI/MCP 调**。当前 **147 已编码 / 0 待编码**。
> 用 `swkit registry --implemented` 只看能直接用的那批（现在两者相等）。

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

## 上游 188 个工具去哪了

`docs/UPSTREAM_AUDIT.md` 是**逐条交代**（由 `tools/audit_upstream.py` 只读生成）：

| 归宿 | 数量 |
|---|---|
| 已覆盖（本仓库有实现 + 真机判据） | 121 |
| 已判死（调用不存在/废弃 API，或实测不可用） | 5 |
| 已知不稳（不进回归） | 2 |
| 未达可用（已登记但没打通） | 18 |
| **未复核（待办）** | 42 |

外加本仓库**超出上游**的 23 条（仿真/运动/元数据、以及上游根本没有的 `sw_cut_extrude`）。

> **两层数字别混淆**：
> * **上游 188 条** → 已覆盖 **111** / 未达可用 **27** / 未复核 **44**（其余判死 4、不稳 2）
> * **registry 的 verified 147** = 上游同名 **121** + 本仓库自有 **26**
>
> 逐条"卡在哪里"见 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md) 的 unverified 分类表
> （参数未定 / 假成功 / 夹具造不出 / 枚举不存在 / 方程接口 / 破坏性不主动做）。

未复核的 44 条已按能力族登记在审计表里，后续按族继续复核。


## 实测环境

- SolidWorks 2025 SP4.1（`RevisionNumber 33.4.1`），Windows x64
- Python 3.10+，`pywin32` / `comtypes` / `mcp>=1.0`
- 验收脚本：[`tests/live_check.py`](tests/live_check.py)（真机，非单测）

一条命令跑全部真机套件（8 个，约 40 s–10 min，取决于 SolidWorks 是否已热）：

```powershell
python tests/run_all.py                       # 全跑，失败会打印每个套件的尾部
python tests/run_all.py --only drawing,balloon # 只跑指定套件
python tests/run_all.py --json out.json        # 机器可读结果
python tests/run_all.py --list                 # 看套件清单
```

pytest 两个入口（真机用例默认**跳过**，见 `tests/conftest.py`）：

```powershell
pytest                 # 只跑离线契约（registry 口径、标记常量、CLI/MCP 结构）
pytest --live          # 连真机一起跑（等价于 run_all.py 的 8 个套件）
```

单套件直跑（排查时用）：

```powershell
python tests/live_check.py     # 装配：组件线性阵列 + 镜像
python tests/part_check.py     # 包围盒/截图/抽壳/特征阵列/分割线/加厚/偏移（8 项）
python tests/sketch_check.py   # 构造线/草图文字/约束/显示状态/材料库（5 项）
python tests/asm_ops_check.py  # 干涉 A/B + 固定/显示/平移/爆炸（4 项）
python tests/drawing_check.py  # 剖视/建图/中心标记/中心线/符号×3/粗糙度/注释/尺寸/孔表/断裂/辅助（13 项）
python tests/balloon_check.py  # 装配图 BOM + 自动球标（2 气球）
python tests/asm_state_check.py # 建装配/插组件/树/抑制/隐藏/替换/特征抑制（11 项）
python tests/mcp_smoke.py      # MCP stdio 握手（不起 SolidWorks）
```

> `serverInfo.version` 显示的是底层 `mcp` 库版本（FastMCP 构造函数没有 version 参数）；
> 本包版本看 `swkit status` 的 `swkit_version`。

### 换机器第一件事：跑 `doctor`（或直接读 [AGENTS.md](AGENTS.md)）

> 仓库自带自检脚本，**跟代码走**——换哪台机器 clone 下来都能跑，不依赖任何本地记忆：

```bash
python scripts/doctor.py          # 人看
python scripts/doctor.py --json   # 机器/agent 读
```

它检查 5 项并给出**可执行**的修法：`python` 版本、`origin` 远端协议、
**SSH key 是否可用**、`comtypes` 是否找得到、SolidWorks 能否连上。

`WARN` 里最重要的一条：**远端如果是 HTTPS 且没有凭据助手，`git push` 会无输出挂死**
（`git-credential-manager` 在等一个你看不见的凭据弹窗——本项目实测挂过 11 分钟）。
所以本仓库远端用 **SSH**；换机器时先 `ssh -T git@github.com` 看到 `Hi <user>!` 再推。

### 本机开发注意（踩过的）

* **`git push` 走 HTTPS 会卡住**：`git-credential-manager` 在没有交互终端时会一直等凭据，
  表现为推送"无输出挂死"。本仓库远端因此改用 **SSH**（`git@github.com:...`），
  或一次性用 `git -c credential.helper="!gh auth git-credential" push`。
  换机器忘了配 key 时，`python scripts/doctor.py` 会直接告诉你 `ssh-keygen` 那三行。
* 提交消息里**不要**用英文双引号包中文（`"...返回 True..."`）——PowerShell 会把字符串
  截断，git 把碎片当 pathspec 报 `pathspec ... did not match`。改用 `git commit -F 文件`。
* 本机 `pytest` 只装在系统 Python（3.12），项目 venv 里没有；跑离线契约测试时用
  `python -m pytest`（系统解释器）+ `PYTHONPATH` 指向 `src` 与该 venv 的 `site-packages`。
* `comtypes` 不在项目 venv 里时：`swkit.core.com.comtypes_bundle()` 会按
  `SWKIT_VENDOR` → `~/.swkit/vendor` → `<repo>/vendor` 顺序自动找。
  本机用目录联接把它挂到 `~/.swkit/vendor`，所以**不需要任何环境变量**即可跑全部真机套件
  （以前漏设 `SWKIT_VENDOR` 会让 7 个套件一起挂在 `No module named comtypes`）。

### 环境变量（都可选）

| 变量 | 作用 | 默认 |
|---|---|---|
| `SW_TLB` / `SWCONST_TLB` | 类型库路径 | `D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\*.tlb` |
| `SWKIT_VENDOR` | 自带 `comtypes` 的目录（找不到时会自动试 `~/.swkit/vendor` 与 `<repo>/vendor`） | 自动查找 |
| `SWKIT_HOME` | 缓存 / 临时输出目录 | `~/.swkit` |
| `SWKIT_DM_DB` | DocumentMgr 索引库 | 有旧索引则沿用，否则 `~/.swkit/swdm_lite.db` |
| `SWKIT_OUT` | 扫描输出目录 | `~/swkit_out` |
| `SWKIT_CHM` / `SWKIT_CHM_DIR` | 官方帮助 `.chm` 与解包目录 | 安装目录 / `%LOCALAPPDATA%\swkit\chm` |

---

## 许可

MIT。上游署名与商标声明见 [`NOTICE.md`](NOTICE.md)。
SOLIDWORKS® 是 Dassault Systèmes SolidWorks Corporation 的注册商标，本项目与官方无关。
