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

## 7. 许可排查（先给出错误结论，后更正）——2026-11-04 01:20–01:35

### 7.1 更正：**不是**"没有 CAM 许可"

先按 `IsCheckedOut("cam_mill")=false` 判成"本机没 CAM 许可"，**这个结论是错的**。
继续查许可文件与 `CheckPresence` 后更正：

```
SPLM_LICENSE_SERVER = C:\ProgramData\Siemens\siemens_SSQ.dat
特性总数 4423（去重 4422），其中 cam_* 相关 695 个，含：
  cam_base · cam_advanced · cam_author · cam_mill · cam_3d_sf_prog
  am_pb_cam_basic · am_pb_cam_advanced · cam_additive_* · cam_ex_kit_post_*

lm.CheckPresence(...)     lm.IsCheckedOut(...)
  cam_base      True        True
  cam_advanced  True        False
  cam_mill      True        False
  am_pb_cam_basic / advanced  True / True    False / False
  gateway       True        True
  design        False       False
```

`IsCheckedOut` 只表示"本会话有没有签出"，**不等于许可不存在**；`CheckPresence` 说明这些
CAM 特性在服务器上是可用的。

### 7.2 那为什么还是不签出 / 不生成

- syslog：`Number of bundles in use : 0`，`Bundle Setting Came From The 'UGS_LICENSE_BUNDLE'
  Environment Variable`，而 `GetBundlesSelected()` 返回 `["None"]`；
- 显式 `lm.SetBundlesForUse(["cam_mill"])` 返回成功（`GetBundlesSelected()` 变成
  `[NumUsing=0,BundleName=cam_mill]`），但 `IsCheckedOut("cam_mill")` **仍是 False**，
  刀路依旧 `path_exists=false`；
- `SetBundlesForUse(["am_pb_cam_basic"])` 等三个包名直接报「切换许可证绑定包失败」；
- Siemens 侧只有 `lmgrd.exe` 两个进程（属于 SolidWorks / Autodesk 的 FlexNet），
  **找不到 ugslmd.exe，28000 端口不监听**。

即：许可文件里特性齐全，但本次 NX 会话始终没有把加工特性签出来，NX 也不报错（静默空刀路）。

### 7.3 毛坯选项在哪（顺手记下来）

不在「加工首选项」里。「加工首选项 → 工序」只有刀轨重播/生成、编辑工序、变换、加工数据、
IPW 后台生成、加工时间计算。

毛坯在**工序对话框**里：双击工序 → 「主要」页 → 「毛坯」，下拉三项：

| 选项 | 含义 |
|---|---|
| 厚度 | 用零件面按厚度偏移当毛坯 |
| 毛坯几何体 | 用几何体组里绑的毛坯（`MCP_WORKPIECE` 的 Blank） |
| 3D IPW | 三维过程工件（本机默认） |

同页还有「指定切削区底面」，之前为空，已补选顶面（`选择对象 (2)`）。

### 7.4 结论

`ug` kit 的 CAM 工具面完整可用（建工序/配几何/配刀具/配进给/查询都验过），卡在
"本机 NX 会话签不出加工许可"这一层，**不在代码里，也不在 CAD-Agent-Hub 的配置里**
（该仓库没有任何 license 配置文件，只在文档里写"需要商业 CAD 软件"）。
要真机验收 CAM，需要这台机器把 Siemens 许可服务跑起来（`ugslmd`）或换一台能签出
CAM 特性的 NX。在那之前工具如实报 `generated_count=0 / path_exists=false`。

## 8. 打通了：第一把真刀路（2026-11-04 01:35–02:00）

### 8.1 重启与许可包实验

按计划做了：存盘（`sheet_metal_model1` 存到 `D:\ProgramData\sheet_metal_model1_backup.prt`，82 KB）→
关 NX → 带 `UGS_LICENSE_BUNDLE` 重启 → 重放 `start_bridge.py` → 桥活（pid 41548）。

许可包实验结论（重要）：

| 尝试 | syslog | 结果 |
|---|---|---|
| `UGS_LICENSE_BUNDLE=am_pb_cam_basic` | `Bundle name too long` + `Number of bundles in use : 0` | 名字超长被拒 |
| `UGS_LICENSE_BUNDLE=FSSSQ`（5 字符） | `Number of bundles in use : 1`、`Bundle [ 0 ] : FSSSQ` | **包生效** |
| 包生效后再生成 | 无任何许可拒绝记录 | 仍然 `path_exists=false` |

→ **许可不是瓶颈**：包里 CAM 特性齐全（`CheckPresence` 全 True），包也成功挂上，
syslog 里没有一条 denied/not-available。之前"缺许可"的判断彻底排除。

### 8.2 真正的阻断点（NX 弹窗原话）

UI 里右键「生成」时 NX 给出两条诊断，一条一条对上：

```
工序参数：当使用 3D IPW 时，毛坯几何体在几何体组被定义。
信息窗口：将"包含毛坯"设置为"毛坯几何体"时，必须在几何体组中指定毛坯几何体。
```

即：**工序的「包含毛坯」模式**和**几何体组的毛坯定义**必须一致。3D IPW 模式下几何体组不许有毛坯；
「毛坯几何体」模式下几何体组必须有毛坯。上游新建工序默认 3D IPW，而 `define_cam_workpiece`
又把毛坯挂进了几何体组 → 两条互斥 → NX 静默拒绝（API 侧只看到 `GetPath` 的 1345083）。

### 8.3 解法与验证

把几何体组的毛坯模式改成 **FromGeometry（毛坯几何体）** 并确保毛坯几何集存在：

```python
wp  = setup.CAMGroupCollection.FindObject("MCP_WORKPIECE")
b   = setup.CAMGroupCollection.CreateMillGeomBuilder(wp)
b.BlankGeometry.BlankDefinitionType = \
    NXOpen.CAM.GeometryGroup.BlankDefinitionTypes.FromGeometry
# 已有空 GeometrySet 就 Selection.Add([毛坯体])，否则 CreateGeometrySet 再 Append
b.Validate(); b.Commit()
```

然后生成——**通了**：

```
ug_generate_cam_toolpath({"operation_names":["OP_FLOOR_FACING"]})
  ok=True  generated_count=1  validation_passed=true
  status "repost"(1)  path_exists=true         ← 之前恒为 "regenerate"(2)/false

ug_inspect_cam_operations
  OP_FLOOR_FACING: status=repost path_exists=true
  其余 6 条仍 regenerate/false（几何/模式还没逐条对齐）
```

`toolpath_length` / `cutting_length` 仍读 0.0（NX 未算统计，不代表无刀轨——`AskPathExists()` 与
状态位翻转是硬证据）。

### 8.4 还没解决的

同一零件里另外 6 条工序（`FACE_MILL_1`、`OP_PLANAR_MILL`、`OP_FACE_MILL_ZIGZAG`、
`OP_TEST2`、`OP_POCKET`、以及干净流程新建的 `OP_FINAL`）仍然生成不出来。
它们的 builder 类型各不相同（`FacingBuilder` / `PlanarMillingBuilder` /
`VolumeBased25DMillingOperationBuilder`），`BlankGeometry` 属性的类型也不同，
"包含毛坯"模式要用各自的方式去设。下一步就是把这组差异逐个补齐，
把"能生成"从 1/7 做到 7/7。

## 9. CAM 刀路配方（2026-11-04 02:00–02:10，2/11 生成成功）

### 9.1 已验证的三条配方

1. **几何体组毛坯**必须是 `FromGeometry`（毛坯几何体）且毛坯几何集非空；
2. **切削区必须同时包含「零件顶面 + 毛坯顶面」两个面**——成功那条的 `CutAreaGeometry`
   是 `[Face 63370 FACE 1 (50,30,20) BLOCK(0), Face 63361 FACE 1 (50,30,20) BLOCK(4)]`，
   只放零件面（其它工序就是这样）不出刀路；
3. **工序级「包含毛坯」= 毛坯几何体**（不是默认的 3D IPW）。

按这三条，`OP_FLOOR_FACING` 与 `OP_FINAL` 两条：

```
status = repost(1)     path_exists = true
```

其余 9 条仍是 `regenerate(2)` / `path_exists=false`。

### 9.2 卡点：工序级「包含毛坯」模式没有 API

新建工序默认 3D IPW；`VolumeBased25DMillingOperationBuilder` 的 89 个属性里只有
`BlankBoundary` / `BlankGeometry` / `WallBlankThickness`，**没有**写这个模式的地方
（`BlankGeometry.BlankDefinitionType` 会抛 `'NXOpen.CAM.Geometry' object has no
attribute 'BlankDefinitionType'`）。只有 UI 里那个下拉能改。

所以现在能做的是：
- 用 UI 逐条把「毛坯」从 `3D IPW` 改成 `毛坯几何体`（每条 3 击：双击工序 → 下拉 → 确定）；
- 或者改 NX 默认（文件 → 实用工具 → 用户默认设置 → 加工 → 工序 → 毛坯），让以后新建的工序
  默认就是毛坯几何体；
- 或者继续找 `CutParameters` 里那层没暴露的 builder（`b.GetCutParameters()` 之类）。

### 9.3 现场

`nsa_verify_cam.prt` 里现在有 11 条工序（含几个试出来的 `OP_POCKET2/3/4`、`OP_POCKET_NEW`），
其中 2 条有刀路。许可包 `FSSSQ` 会话仍在运行，桥在 48161。

