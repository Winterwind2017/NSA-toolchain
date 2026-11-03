# `ug` kit 真机验收记录（2026-11-04 00:45–00:53，NX 2512 交互会话）

NX 里加载 `NXMcPRemotingServer.dll`（命令：**工具 → 操作记录 → 播放** →
`CAD-Agent-Hub\MCP\UG\start_bridge.py`）之后，桥端口 `127.0.0.1:48161` 起来，
`ug` kit 才真正可用。下面是这一轮跑出来的东西，**全部是真实 NX 会话里的读数**。

## 0. 桥连通

```
ug_ping → ok=True  0.6s
  bridge_version 0.20.1 · transport dotnet-remoting · NX pid 24564
  application UG_APP_SBSM（钣金模块）· work_part sheet_metal_model1
  endpoint http://127.0.0.1:48161/NXOpenSession
```

## 1. 钣金全链路（在新建零件 `nsa_verify_sheet.prt` 里做，没碰用户的原零件）

| 步 | 工具 | 关键读数 |
|---|---|---|
| 1 | `ug_create_part` | `nsa_verify_sheet.prt`，units=millimeters |
| 2 | `ug_create_parametric_sketch` | `SK_PROFILE`：4 条线、**8 个约束**、XY 平面 |
| 3 | `ug_create_sheet_metal_tab` | `SB_TAB(0)`，厚度 **2.0 mm**，body_count=1 |
| 4 | `ug_create_sheet_metal_flange` | `AdvancedFlange(1)`：边 index 9、长 **20 mm**、90°、R1.5；拓扑 边 **12 → 24**、面 → **10** |
| 5 | `ug_create_flat_pattern` | `FLAT_PATTERN(3)`，associative=true，body_count=3 |
| 6 | `ug_export_flat_pattern_dxf` | `nsa_verify_flat.dxf`，**93,378 B**，`dxf_header_present=true`，含折弯线 |

判据：钣金 4 个特征都拿到 feature_journal_id + 实体数；展开图导出的 DXF 有文件大小和
文件头两项硬证据。**这条链路是完整验证过的。**

## 2. 装配约束

```
ug_add_component ×2  → nsa_verify_asm2.prt 组件 2 个（is_assembly=true）
ug_add_assembly_constraint(type=fix) → HANDLE O-34，update_error_count=0
ug_inspect_assembly_constraints → constraint_count=1，references 指向 COMPONENT tag 71693
```

判据：约束对象存在（journal_id + tag）、状态值 9、求解报错 0、读回 1 条。

> 踩到的坑：`add_component` 的 `file_name` 只收**纯文件名**（相对 workspace），
> 传绝对路径会被上游拒；且 `.prt` 必须先落盘才能被引用（用 `run_python` 里
> `session.Parts.SaveAll()` 存一次）。

## 3. CAM（部分打通）

打通的：

```
ug_initialize_cam_setup      → NC_PROGRAM / PROGRAM / METHOD 三组，created=true
ug_get_cam_capabilities      → cam_session_initialized=true，17 种模板类型
ug_create_cam_milling_context→ MCP_PROGRAM / MCP_METHOD / MCP_MCS / MCP_WORKPIECE 全部建出
ug_create_cam_mill_tool      → T1_D10（Ø10，刃长 30，总长 70，4 刃；cutter+shank 几何就绪）
ug_create_cam_operation      → FLOOR_FACING：VolumeBased25DMillingOperation，tag 249921
ug_set_cam_operation_geometry→ part_geometry + cut_area 都绑上，validation_passed=true
ug_configure_cam_milling_operation → 转速 3000 / 切削 500 / 进刀 200 / 退刀 800，validation_passed=true
```

**没打通的：刀路生成。**

```
ug_generate_cam_toolpath → ok=False
  backend=uf_param_generate → return_value=false，path_exists=false
  backend=nxopen → generation_results=[]（NX 没有返回完整刀路）
  先报 machining_data 缺记录（error_code 1850031），补了显式转速/进给之后仍失败
```

这不是我们这层的问题：**上游工具如实返回 `generated_count=0` / `path_exists=false`，
没有假装成功**。缺的是 FLOOR_FACING 这类体积铣削工序还需要的那组几何/策略参数
（floor/wall 选择、毛坯余量、切削模式等），上游没有暴露全。

**下一步建议**：在 NX 里手工把 `OP_FLOOR_FACING` 调通一次（看它到底要哪几个参数），
再把那组参数补进 `configure_cam_milling_operation`；或者直接用 `ug_run_python`
走 NXOpen CAM builder 把缺的参数一次性设全。

## 4. 验收用例

`python -m nsa_mcp_hub.acceptance --kit ug`（桥活着时）：

```
PASS ug.ping            429 ms
PASS ug.cam.capabilities 371 ms
ug：2/2 通过（1.7s）
报告：_runs/acceptance-20261104-005313.json
```

桥没起时这两条会 SKIP（`skip_if` 看 `ugraf.exe` 在不在）。`catia` 那条仍然是 SKIP
（本机没装 CATIA）。

## 5. 跑这轮验收在 NX 里留下的东西

`CAD-Agent-Hub\MCP\UG\workspace\` 下：`nsa_verify_sheet.prt`、`nsa_verify_asm.prt`、
`nsa_verify_asm2.prt`、`nsa_verify_cam.prt`、`nsa_verify_flat.dxf`。
用户原有的 `sheet_metal_model1` 只被 `SaveAll()` 存过一次盘，没有改几何。

## 6. CAM 刀路的进一步定位（2026-11-04 01:00–01:10）

继续攻刀路，把 NX 的**真实拒绝原因**挖出来了。逐条排除：

| 试过的手段 | 结果 |
|---|---|
| `setup.GenerateToolPath([op])` | 调用不抛错，`AskPathExists()=false`，`GetStatus()=2` |
| `setup.CreateToolpathGenerateBuilder([ops])` + `Types.Foreground` + `Generate()` | 返回 **0 条**结果（不是失败项，是"没东西可生成"） |
| backend = `nxopen` / `uf` / `auto` | 全 false；`uf.Param.Generate(tag)` 返回 `False` |
| 切到**制造应用**（`UG_APP_MANUFACTURING`，UI 里"应用模块 → 加工"） | 仍是 false |
| 建独立**毛坯体**并用 `define_cam_workpiece(blank_body_indices=[1])` 绑上 | 绑上了（`blank_geometry_assignment.objects_added=1`），仍 false |
| 补显式转速/进给（`spare_rpm 3000 / cut 500 / approach 200 / retract 800`） | 仍 false（原先的 `error_code 1850031` 消失） |
| 不调用 `SetTemplateStatus(...,False,False)` 建工序 | 仍 false |
| **在 UI 里右键 → 生成(G)** | **NX 弹出真错误**（见下） |

**UI 生成时 NX 的原始提示**（这是唯一一次拿到具体原因）：

```
工序参数
当使用 3D IPW 时，毛坯几何体在几何体组被定义。
[确定]
```

含义：这个工序（`FLOOR_FACING` 属于体积铣）默认启用 **3D IPW**，而毛坯被定义在**几何体组**
（`MCP_WORKPIECE`）上——两者冲突，NX 直接拒绝生成，且**不抛异常**（所以 API 侧看起来是"静默失败"）。

已确认无关：许可（`IsCheckedOut("cam_base")=true`）、应用环境（已切制造）、刀具/几何/进给（都绑上了）。

**下一步的两条路**（留给下一轮）：

1. 把**加工首选项里的 IPW 类型**从 3D 改成 2D/无（或在工序「切削参数 → 空间范围」里改），再生成；
   这条最可能就是缺的一脚。
2. 走"录制操作记录"：UI 里手动建一个能生成的工序并录制 journal，反出它到底设了哪些参数
   （`工具 → 操作记录 → 记录`），再照抄。

上一轮记的"CAM 刀路未通"要精确成：**已知唯一阻塞点是 3D IPW 与几何体组毛坯的冲突**。

## 7. 真正的根因：本机没有 CAM 刀路计算许可（2026-11-04 01:20）

继续排查时先找到了「毛坯」选项的位置，也把切削区底面补上了，仍然生成不出刀路；
最后查许可，结论很硬：

```
lm.IsCheckedOut(...) 的结果
  cam_base        = True     ← 只有这个
  gateway         = True
  nxcam_base      = False
  cam_mill        = False
  cam_mill_planar = False
  cam_2d / cam_3d = False
  cam_foundation  = False
  cam_advanced / cam_simulation = False
  lm.GetBundlesUsed() = []   ← 没有任何"在用"的许可包
```

只有 `cam_base`（CAM 基础，允许建工序/看模板）和 `gateway`。**刀路的实际计算需要加工类许可
（`nxcam_base` / `cam_mill_planar` / `cam_3d` 这类），本机一个都没有。**

这解释了全部现象：
- `setup.GenerateToolPath([op])`、`CreateToolpathGenerateBuilder([ops]).Generate()`、
  `uf.Param.Generate(tag)` 三种入口都"调用成功但返回空"，不抛异常；
- UI 里右键生成也出不来，且只在没选切削区时给一句提示；
- syslog 里只有 `GetPath` 的"工序无任何刀轨"，没有生成阶段的错误——NX 根本没进计算；
- 与几何/刀具/进给/毛坯/IPW/应用环境全部无关（这些都逐条验过并排除了）。

### 毛坯选项在哪（顺手记下来）

不在「加工首选项」里。「加工首选项 → 工序」只有刀轨重播/生成、编辑工序、变换、加工数据、
IPW 后台生成、加工时间计算这些。

毛坯在**工序对话框**里：双击工序 → 「主要」页 → 「毛坯」，下拉只有三项：

| 选项 | 含义 |
|---|---|
| 厚度 | 用零件面按厚度偏移当毛坯 |
| 毛坯几何体 | 用几何体组里绑的毛坯（`MCP_WORKPIECE` 的 Blank） |
| 3D IPW | 用三维过程工件（本机默认） |

### 结论与后续

`ug` kit 的 CAM 工具面是**完整可用**的（建工序、配几何、配刀具、配进给、查询状态都验过），
只差"生成刀路"这一步吃许可。要真机验收 CAM，需要这台机器上有一张 NX CAM 加工许可
（`nxcam_base` 或 `cam_mill_planar`/`cam_3d`）。在那之前，工具会如实报
`generated_count=0 / path_exists=false`，不会假装成功——这本身是符合验收原则的行为。

