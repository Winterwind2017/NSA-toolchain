# nxkit 收口报告

引擎 **NX 2512**（`D:\Program Files\Siemens\DesigncenterNX2512`），内核 **nxkit 0.1.0**，技能 **ww-nx-automation**。

## 1. 结果

| 指标 | 数值 |
|---|---|
| 真机通过能力 | **146** |
| 其中带 L4（存盘→重开→复测） | **54** |
| 一次会话跑完全部能力 | ~47 s（DXF/DWG 两次翻译器启动各约 17 s） |
| 未打通（每条都有 NX 原文错误） | **7** |
| 离线测试 / 技能校验 | 9 passed / 通过 |

### 按族

| family | 能力数 | L4 |
|---|---:|---:|
| feature | 34 | 29 |
| sketch | 18 | 2 |
| drawing | 14 | 0 |
| curve | 11 | 0 |
| solid | 11 | 8 |
| attr | 10 | 2 |
| export | 9 | 0 |
| assembly | 8 | 1 |
| boolean | 7 | 7 |
| inspect | 6 | 0 |
| measure | 6 | 2 |
| surface | 6 | 1 |
| part | 4 | 1 |
| file | 2 | 1 |

## 2. 怎么做的

### 2.1 一个会话只跑一次 NX

主机侧生成 job（JSON）→ `run_journal.exe journal.py -nx` 一次拉起 NX → `nxkit.runtime.actions` 逐条造几何/读读数 → 主机侧判分。NX 退出码恒为 1，只认 `result.json`。

### 2.2 判据全部从 NX 读回

四层：L1 计数（体/面/边/视图/实体）、L2 属性（体积/面积/长度/间距/重心）、L3 几何关系（体积守恒、面积回归、重心位移）、L4 存盘→重开→复测。容差按量级分档：≥100 → 0.5，≥1 → 1e-3，其余 1e-6。

### 2.3 批量探针是最大的效率杠杆

一个探针脚本在一次 NX 会话里试 4–6 个 builder × 多组参数，输出一行 `BATCHn <json>`；`_nx_recon/batch1..45.py` 是全过程留档。早期是「一个变体一次会话（~25 s）」。

### 2.4 新增能力只走 `tools/add_cap.py`

锚点插入（`\nACTIONS = {` / `ACTIONS = {\n` / `CAPS: tuple[Cap, ...] = (\n`）+ `py_compile` + `selftest`，并**硬检查 cap id 唯一**（曾因撞名产生 145 条 / 144 唯一）。

## 3. 判死的 7 项

| 项 | 卡在哪 |
|---|---|
| `cam.setup` | 模块入口全 None（CreateCamSetup 四种模板都返回 None，CAMSetup 抛 1345023） |
| `cae.mesh` | NXOpen.CAE 无可用 builder |
| `sketch.constant_length` | NX 明确拒建（Unable to create sketch geometric constraint）；语义相近的 equal_length 已通 |
| `drawing.section_view` | ParentView 不可写、无集合方法可绕；SectionView.Null 构造后 Commit 报 Null tag not allowed |
| `solid.delete_body` | BodyToDelete 与 BodyToKeep 两个 collector 都是 None，Commit 报 Missing target body；删面/修剪/求差可部分替代 |
| `sketch.point_on_curve` | 约束能建，但 Sketch 没有 Solve，Deactivate 后几何不动 |
| `sheet_metal.flange` | SilhouetteFlange 方向被拒、AdvancedFlange 报 edges must be tangent continuous；根因是绑定里没有钣金基体/Tab 创建器 |

按卡点归类：

- **服务对象 NX 不给工厂**：`delete_body`（两个 collector 都是 None）
- **入口只读、且无集合方法可绕**：`drawing.section_view`、`sketch.point_on_curve`
- **控制器空转**：`sketch.point_on_curve`（约束建好但几何不动）
- **NX 直接拒建**：`sketch.constant_length`、`sheet_metal.flange`（edges must be tangent continuous）
- **环境缺模块/基体**：`cam.setup`、`cae.mesh`、`sheet_metal`（无钣金基体创建器）

## 4. 收口阶段翻案的（原判死，其实有门）

| 条目 | 真正的入口 | 结果 |
|---|---|---|
| `curve.bridge` | 属性只读但它返回的 `SelectObject` 可写：`StartObject.Value` | 1 条 Spline，弦长 63.246 |
| `curve.intersection` | `FirstFace/SecondFace` 是 `ScCollector`（AddRules）+ **`Tolerance>0`** | 直线 (0,0,0)→(100,0,0) |
| `export.dxf` / `export.dwg` | NX 自带翻译器 CLI `NXBIN\dxfdwg.exe <part> o= l= d= m=ugtodxf`；def 里 `UGI_DRAWING_NAMES` 默认空导致导不出 | 190 KB DXF / 18 KB DWG（AC1018） |
| `solid.move_body` | `CreateMoveBodyBuilder(MoveBody.Null)` + **`ModlMotion.Option=Distance`** | 重心 50 → 150 |
| `feature.text` | `CreateCoordinateSystem(origin, Matrix3x3, is_temporary: bool)` | NXTEST → 6 条 Spline |
| `surface.offset` | `OffsetSurfaceBuilder` 死路 → 改 `VariableOffsetBuilder` | 2 片、间距 5.0 |

另有 4 项属**重复需求**，已从「未打通」移出：`pattern.body_linear`（`feature.pattern_linear` 已覆盖）、`feature.revolve_datum`（`feature.revolve` 已覆盖）、`feature.chamfer` / `feature.chamfer_angle`（早已验证，文档陈旧）。

## 5. 复现

```powershell
$env:PYTHONPATH='D:\bililive\nxkit\src'
python -m nxkit run --workdir D:\bililive\nxkit\_runs\check   # 146/146 通过，约 47 s
python -m nxkit selftest       # 146 条，动作/判据齐全，负例被拒
python -m pytest -q tests      # 9 passed
python tools\check_consistency.py --skill D:\bililive\ww-nx-automation   # 五处数字一致
```

## 6. 已知边界

- 只在本机 NX 2512 + 4,422 特性许可下验证；
- `run_journal` 退出码恒 1，不要用退出码判成败；
- 依赖交互式选择/求解器的功能（装配求解、剖视图、实体阵列的 PatternBody）journal 下拿不到上下文；
- `DxfdwgCreator.Commit()` 在 journal 里是空操作，DXF/DWG 必须走翻译器 CLI。

