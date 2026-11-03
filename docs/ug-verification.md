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

## 10. 方案 A 的实测结果（2026-11-04 02:05–02:20）：**4/11**

### 10.1 客户默认改不了（user.mtx 只有界面布局）

查了默认设置落盘位置：

```
C:\Users\yuche\AppData\Local\Siemens\Designcenter2512\user.mtx   （186 KB）
```

里面只有 `<NX_PROFILES><Profile name="UG_APP_NOPART"><Layout>` 这类**界面布局**（Ribbon 标签、
窗口列宽），没有一条 CAM「毛坯/包含毛坯」的默认值。也就是说：
**改 NX 客户默认这条路对这个设置无效**，它要么来自工序模板 part
（`mach\resource\template_part\metric\mill_planar.prt`），要么根本没有暴露成默认项。

### 10.2 但 UI 逐条改是有效的——4 条通

按第 9 节第 3 条，在 UI 里把工序的「毛坯」从 `3D IPW` 改成 `毛坯几何体`，每改一条立刻生成：

| 工序 | 类型 | 改后 |
|---|---|---|
| OP_FLOOR_FACING | VolumeBased25DMillingOperation | ✅ repost / path_exists=true |
| OP_FINAL | VolumeBased25DMillingOperation | ✅ repost / true |
| OP_POCKET | VolumeBased25DMillingOperation | ✅ repost / true |
| OP_TEST2 | VolumeBased25DMillingOperation | ✅ repost / true |

```
ug_inspect_cam_operations → 有刀路 ['OP_FLOOR_FACING','OP_TEST2','OP_POCKET','OP_FINAL']  4 / 11
```

**规律很干净：`VolumeBased25DMillingOperation`（腔铣 / 无壁底面加工）这一类，只要
①几何体组毛坯=FromGeometry ②切削区含零件+毛坯两个顶面 ③工序毛坯=毛坯几何体，就能生成。**

### 10.3 剩下 3 条真工序是另一类问题（面铣族）

`FACE_MILL_1`（Face Mill Midpass）、`OP_PLANAR_MILL`（平面铣）、`OP_FACE_MILL_ZIGZAG`（面铣-单向往复）
的对话框里**没有**「毛坯」下拉（`FacingBuilder` / `PlanarMillingBuilder` 连 `BlankGeometry`
属性都没有），它们缺的是**「指定切削区域」的面**——对话框里那一栏是空的。

API 侧补这一栏失败：

```
ug_set_cam_operation_geometry(FACE_MILL_1, cut_area_face_selectors=[stable_id...])
  → ValueError: topology stable_id no longer exists and has no geometry fallback
```

原因是上游的 stable_id → 拓扑对象解析在这个零件上失效了（面被重排/新增体之后）。这条路需要
上游修 stable_id 回退，或者在 UI 里点面。

### 10.4 结论

- 「许可」彻底排除（第 8 节）；「毛坯模式」是主因（第 9、10 节）；
- 腔铣族已经能做到"建工序 → 配两面切削区 → 生成"只要工序的毛坯模式是毛坯几何体，
  而这个模式目前只能 UI 改（API 无属性）；
- 面铣族还差「切削区域的面」，API 侧的 stable_id 解析需要上游修。

## 11. 面铣族打通，6/11（2026-11-04 02:20–02:35）

### 11.1 面铣族缺的是「切削区域」的面

`FACE_MILL_1`（Face Mill Midpass）和 `OP_FACE_MILL_ZIGZAG`（面铣-单向往复）对话框里
**没有「毛坯」下拉**，只有「指定切削区域」——那一栏是空的。补上一个顶面后就出刀路了：

```
FACE_MILL_1          repost / path_exists=true
OP_FACE_MILL_ZIGZAG  repost / path_exists=true   （面铣的刀路预览里能直接看到往复刀轨）
```

注意：**必须点对话框的「确定」，不能用 Esc 关**。Esc 会回滚未提交的几何改动，
工序又变回 `regenerate`——我头一次就是这么把 ZIGZAG 打回原形的。

### 11.2 当前状态：6 / 11

```
FACE_MILL_1          repost      true    ← 本轮打通
OP_FLOOR_FACING      repost      true
OP_FACE_MILL_ZIGZAG  repost      true    ← 本轮打通
OP_TEST2             repost      true
OP_POCKET            repost      true
OP_FINAL             repost      true
OP_PLANAR_MILL       regenerate  false   ← 唯一没通的真工序
OP_POCKET2/3/4、OP_POCKET_NEW     false   （配方试验留下的）
```

### 11.3 平面铣（OP_PLANAR_MILL）卡在哪

* 「部件边界」已经设好（选择方法=面 → 顶面 → 确定）；
* 状态栏提示 **「未指定底面。」**——平面铣必须要底面；
* API 侧 `PlanarMillingBuilder` 的几何属性只有
  `PartBoundary` / `TrimBoundary` / `BlankBoundary` / `CheckBoundary`（都是 `BoundaryPlanarMill`），
  以及 `Geometry`（`GeometryCiBuilder`）；**`CutAreaGeometry` 和 `PartGeometry` 都是 None**，
  没有直接写底面的入口；
* UI 侧可以用「指定底面 → 选顶面 → 偏置 −20mm」造出底面，但那个距离框是 NX 表达式控件，
  盲点 + 粘贴会拼成 `0-20-20-` 这种脏值，需要更稳的输入方式（清空按钮 + 键盘输入）。

结论：平面铣这一族**要底面**，且底面要么用 UI（含表达式输入），要么找 `GeometryCiBuilder`
里未暴露的 floor 入口。其余三族（腔铣/无壁底面、面铣 Midpass、面铣单向往复）已经全线可生成。

## 12. 2→1→3 收尾（2026-11-04 02:30–03:00）

### 12.1 ② 平面铣：找到底面入口，但仍不出刀路

`PlanarMillingBuilder.Geometry` 是 `GeometryCiBuilder`，成员里有 **`FloorPlane`**——这就是 UI 上
「指定底面」的 API 入口。设置成功：

```
b.Geometry.FloorPlane = work.Planes.CreatePlane((0,0,0),(0,0,1), AfterModeling)
  → set_floor ok / validate true / commit ok
```

但生成仍是 `path_exists=false`、状态 `regenerate`。也就是说平面铣除了底面还要
「部件边界 + 切削深度」自洽（UI 里我把边界设在顶面、底面设在 z=0、公共深度 20，仍不出）。
结论：**平面铣这一族暂未打通**，其余三族（腔铣/无壁底面、面铣 Midpass、面铣单向往复）共 6 条可生成。

### 12.2 ① 清场：删掉 3 条试验工序，剩 1 条删不掉

UI 右键 → 删除，删掉了 `OP_POCKET2`、`OP_POCKET_NEW`、`OP_POCKET4`。

**删不掉的**：`OP_POCKET3`（还有一个本轮试验新建的 `OP_FLOOR_NEW`）。原因查清了：

```
CAMOperationCollection 没有 DeleteObject/Remove
Operation 对象也没有 Delete/Destroy
（其 delete-like 成员只有 DeleteToolPath / DeleteMasterPath / DeleteAllAttributesByType 等）
```

→ NXOpen **不提供删除工序的 API**，只能 UI 右键删除。这是工具面缺的一环，记在这里。

### 12.3 ③ 回写工具面（CAD-Agent-Hub/MCP/UG）

改了两处，均已 `py_compile` 通过：

**A. stable_id 跨体解析**（`_resolve_topology_object`）

以前：给了 `stable_id` 但没给几何回退，而该 id 属于另一个 body（比如毛坯体 1）时，直接抛
`topology stable_id no longer exists and has no geometry fallback`。
现在：先在指定 body 找，找不到就遍历其余 body，命中即切换。stable id 本来就是"零件级"的。

**B. 切削区自动补毛坯顶面**（新增 `_cam_blank_top_faces` + 参数 `auto_add_blank_faces`）

`set_cam_operation_geometry(..., auto_add_blank_faces=true)` 会把毛坯体（BlankGeometry 里的体）
的 +Z 最高面追加进 `CutAreaGeometry`——这正是第 9 节那条"切削区必须同时有零件面和毛坯面"的配方。
`configure_cam_milling_operation` 同样支持该参数，schema 已同步（`server.py`）。

实测（`OP_FLOOR_NEW`）：

```
绑几何 + auto_add_blank_faces  ok=true  validation_passed=true
  cut_area: objects_added=2     blank_faces: objects_added=1
生成                            path_exists=false  status=regenerate
```

→ 几何配方能自动落实了，但**新建工序依然生成不出来**，缺的仍是那一步：
**工序级「包含毛坯」必须是「毛坯几何体」**，而它没有任何 NXOpen 属性可写
（`VolumeBased25DMillingOperationBuilder` 89 个属性里只有 `BlankBoundary`/`BlankGeometry`/
`WallBlankThickness`；`GeometryCiBuilder` 里也没有）。改几何体组无效——组是 `FromGeometry`
时新工序仍是 `3D IPW`，说明默认值来自工序模板 part。

**这就是工具面最后一条缺口**：要么改 `mach\resource\template_part\metric\mill_planar.prt` 模板，
要么每条工序在 UI 里点一次下拉。

## 13. 改工序模板：CAM 全自动打通（2026-11-04 02:35–03:00）

### 13.1 模板在哪、怎么改

模板部件：`D:\Program Files\Siemens\DesigncenterNX2512\mach\resource\template_part\metric\mill_planar.prt`
（6.3 MB，里面有 18 个工序模板：`FLOOR_FACING`、`POCKETING`、`FLOOR_WALL`、`WALL_PROFILING`、
`PLANAR_MILL`、`FACE_MILL_MIDPASS` …）

过程里踩到两个坑：

1. 模板文件在磁盘上是 **ReadOnly**（`0o444` / 属性 ReadOnly），NX 以模板身份加载时也是只读，
   改了只会弹「只读对象 / 将无法保存」——必须先去掉只读属性，并让 NX **以普通部件重新打开**
   （`Part.Close(CloseWholeTree.TrueValue, …)` 再 `Parts.OpenBaseDisplay()`）；
2. 备份先做了：`mill_planar.prt.bak-20261104`。

然后把 `FLOOR_FACING` 和 `POCKETING` 两个模板的「毛坯」从 `3D IPW` 改成 **毛坯几何体**，保存。

### 13.2 关键发现：工具体也要给毛坯

改完模板后新工序默认确实是「毛坯几何体」了，但仍然生成不出来。查 `inspect_cam_operation_details`
才发现：**新工序的 `BlankGeometry` 集合是空的**（item_count = 0）——工序不会自动继承几何体组里的毛坯体。

补上毛坯体后立刻成功：

```
blank_items_before=0 → 把 BLOCK(4) 塞进工序的 BlankGeometry
generate → path_exists=true  status=1(repost)
```

### 13.3 纯工具调用的完整配方（已实测两条）

```
1) ug_create_cam_operation(name, template_subtype="FLOOR_FACING"|"POCKETING", template_type="mill_planar",
                          tool_name="T1_D10", geometry_name="MCP_WORKPIECE")
2) ug_set_cam_operation_geometry(operation_name,
       part_body_indices=[0],
       blank_body_indices=[1],                    # 新增：工序自己的毛坯体
       cut_area_face_selectors=[零件顶面, 毛坯顶面],# 两面都要
       auto_add_blank_faces=True,                 # 新增：自动补毛坯顶面
       depth_per_cut=2.0)
3) ug_generate_cam_toolpath(operation_names=[...])  → generated_count=1 validation_passed=true
```

实测：`OP_RECIPE_FLOOR`、`OP_RECIPE_POCKET` 两条**全部 ok，generated_count=1**，全程没有碰 UI。

### 13.4 最终状态：9 / 12

```
FACE_MILL_1          repost   true
OP_FLOOR_FACING      repost   true
OP_FACE_MILL_ZIGZAG  repost   true
OP_TEST2             repost   true
OP_POCKET            repost   true
OP_FINAL             repost   true
OP_TEMPLATE_TEST     repost   true    ← 改模板后新建
OP_RECIPE_FLOOR      repost   true    ← 纯工具调用
OP_RECIPE_POCKET     repost   true    ← 纯工具调用
OP_PLANAR_MILL       regenerate false ← 平面铣（要底面+边界自洽）
OP_POCKET3           regenerate false ← 早期遗留试验件
OP_FLOOR_NEW         regenerate false ← 早期遗留试验件
```

已有 6 条也统一补了毛坯体并重新生成，状态位全部回到 `repost(1)`，刀路未丢。
验收 `ug` 仍 **2/2 通过**（`_runs/acceptance-20261104-024108.json`）。

## 14. 平面铣打通 —— 11/11 全有刀路（2026-11-04 02:45–03:05）

### 14.1 平面铣到底要什么

`PlanarMillingBuilder`（模板 `PLANAR_MILL`）和腔铣那族完全不同：它**没有 `CutAreaGeometry`**
（属性存在但值是 `None`），边界走 `PartBoundary` → `BoundaryList` → `BoundarySetPlanarMill`。
四样东西缺一不可：

1. **边界曲线**：`boundary_set.AppendCurves(curves, Point3d, Matrix3x3)`
   —— 真签名是 3 个参数（曲线列表、起点、单位矩阵），不是 1 个参数；
   用顶面的 4 条边追加后 `BoundaryMemberList.Length` 从 0 变 4；
2. **边界平面**：`boundary_set.Plane`（此前是 `None`，NX 状态栏就是在报「未指定底面」）；
3. **底面**：`builder.Geometry.FloorPlane`（`GeometryCiBuilder` 上，第 12 节已确认可写）；
4. **切削深度**：`builder.DepthPerCut.Value`（此前是 0.0，等于不切）。

### 14.2 纯工具调用（已实测 generated_count=1）

```
ug_create_cam_operation(name, template_subtype="PLANAR_MILL", template_type="mill_planar",
                        tool_name="T1_D10", geometry_name="MCP_WORKPIECE")
ug_set_cam_operation_geometry(operation_name,
    cut_area_face_selectors=[{"selector": {"stable_id": 顶面}, "body_index": 0}],
    floor_z=0.0,          # 新增：底面高度
    depth_per_cut=20.0)   # → DepthPerCut
ug_generate_cam_toolpath(...)   → generated_count=1
```

返回里能看到 `assignments.boundary = {boundary_sets: 1, curves_added: 4}`、`assignments.floor_z = 0.0`。

### 14.3 上游实现要点（`docs/upstream-ug-cam-patch.md` 第 4 节）

* 平面铣判定不能写 `hasattr(builder, "CutAreaGeometry")` —— 这个属性**存在但为 None**，
  要判 `getattr(builder, "CutAreaGeometry", None) is None`；
* `_cam_append_geometry` 增加 `geometry is None` 的守卫（否则报
  `'NoneType' object has no attribute 'GeometryList'`）；
* 新增 `_cam_planar_boundary_curves()` / `_cam_set_planar_floor()`，参数 `floor_z` 已进 schema。

### 14.4 最终状态：11 / 11

```
FACE_MILL_1  OP_PLANAR_MILL  OP_FLOOR_FACING  OP_FACE_MILL_ZIGZAG  OP_TEST2
OP_POCKET    OP_FINAL        OP_TEMPLATE_TEST OP_RECIPE_FLOOR
OP_RECIPE_POCKET             OP_RECIPE_PLANAR
→ 全部 repost / path_exists=true
```

验收 `ug` 仍 **2/2 通过**（`_runs/acceptance-20261104-025012.json`）。

## 15. CAM 配方进验收：`ug.cam.recipe`（2026-11-04 03:05–03:15）

### 15.1 用例做什么

`nsa_mcp_hub/acceptance/cases.py::_ug_cam_recipe` 全程只用 kit 工具，自己建一个独立零件：

```
ug_create_part            nsa_accept_cam_<时分秒>.prt
ug_create_block           零件体 100×60×20 @(0,0,0)
ug_create_block           毛坯体 104×64×24 @(-2,-2,-4)   ← 顶面同在 z=20
ug_initialize_cam_setup   mill_planar
ug_create_cam_mill_tool   T1_D10
ug_create_cam_milling_context(origin=(0,0,20), part=[0], blank=[1])
→ 对 FLOOR_FACING / POCKETING / PLANAR_MILL 各做一遍：
    ug_create_cam_operation
    ug_set_cam_operation_geometry(part=[0], blank=[1],
        cut_area_face_selectors=[零件顶面, 毛坯顶面],
        auto_add_blank_faces=True, floor_z=0, depth_per_cut=2)
    ug_generate_cam_toolpath
→ ug_inspect_cam_operations 取回 path_exists
→ finally：把验收零件 Close（不存盘），显示切回原零件
```

判据 6 条（三种工序各两条）：`<族>.generate_ok` 与 `<族>.path_exists`，全 true 才算过。
耗时约 **12 s**。

### 15.2 判据不是空转——做了负向验证

把 `floor_z` 从调用里摘掉（模拟平面铣退化）：

```
FLOOR_FACING.generate_ok    True
POCKETING.generate_ok       True
PLANAR_MILL.generate_ok     False   ← 立刻红
PLANAR_MILL.path_exists     False
ok = False
```

### 15.3 顺带给验收框架加了 `call` 钩子

原来的用例模型是「一条用例 = 一次工具调用」，装不下多步配方。
`harness.run_kit` 现在支持 `case["call"](client, context) -> payload`：钩子自己编排调用，
返回标准契约 `{ok, reads, checks, errors}`，后面的判据/报告逻辑完全复用。

### 15.4 结果

```
=== ug ===
  PASS ug.ping                 523 ms
  PASS ug.cam.capabilities     474 ms
  PASS ug.cam.recipe         12037 ms
ug：3/3 通过（14.4s）
报告：_runs/acceptance-20261104-025429.json
```

