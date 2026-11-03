# CAD-Agent-Hub 的 SolidWorks 部分：40 个工具的拆解与并入结论

> 来源：`D:\bililive\CAD-Agent-Hub\MCP\Solidworks\src\solidworks_mcp`（MIT，Copyright (c) 2026 Cai-aa）
> 对照目标：本机 `kit-sw`（并入前 155 个工具，其中 swkit MCP 代理 145 个 + mcp-patches 脚本 10 个）
> 拆解时间：2026-11-02

## 一、结论摘要

| 处置 | 数量 | 说明 |
|---|---|---|
| **已并入**（纯算法，本轮完成） | 6 个工具 → 5 个新工具 | 齿轮/减速器/输出轴/参数化零件/特征图编译，判据是数学 |
| **待并入**（需要 COM 执行层） | 12 个 | 特征图执行、特征树编辑、自审查、会话管理 |
| **不并入**（我们已有等价物且更贴合本机） | 20 个 | 见逐条表 |
| **不并入**（对本架构无意义） | 2 个 | `reload_runtime`、`create_sphere` |

并入后 `kit-sw`：**155 → 165 个工具**（计划层 5 + 特征树 4 + 执行层 1）。

## 二、逐工具拆解（40 条）

「我们已有」列里写的是本机 `kit-sw` 里对应的工具名。

### A. 会话 / 文档（9）

| hub 工具 | 参数 | 我们已有 | 差异与结论 |
|---|---|---|---|
| `health_check` | 0 | `sw_status` | 它强调「不启动 SolidWorks」；我们的 `sw_status` 也不启动。**不并入** |
| `operation_status` | 0 | — | **「不进 COM 队列就能查忙闲」**——我们的单飞锁是阻塞式，没有旁路查询。**借鉴技术，不整搬** |
| `connect(start_if_missing)` | 1 | `sw_connect` | 等价。**不并入** |
| `list_documents` | 1 | `sw_list_open_documents` | 它有 **dirty（未保存）标记**，我们没有。**待并入（小改动）** |
| `activate_document(title)` | 2 | — | 只能按标题激活已开文档，我们没有。**待并入** |
| `open_document(path)` | 2 | `sw_open_document` | 它明确支持 STEP 导入为零件；我们的走 `sw_open_document`（未验证 STEP）。**待确认** |
| `save_active` | 2 | `sw_save_document` | 等价。**不并入** |
| `reload_runtime` | 0 | — | 它自己的模块热重载，与本架构无关。**不并入** |
| `export_active` | 2 | `sw_export_file/step/iges/stl` | 我们是分格式的多个工具，更细。**不并入** |

### B. 几何度量（2）

| hub 工具 | 我们已有 | 结论 |
|---|---|---|
| `get_bounding_box(include_hidden)` | `sw_bounding_box` | 它有 `include_hidden` 选项，我们没有。**待并入（加参数）** |
| `get_mass_properties` | `sw_get_mass_properties` | 等价（它多返回主惯性矩）。**不并入** |

### C. 重建 / 自审查（3）

| hub 工具 | 我们已有 | 差异与结论 |
|---|---|---|
| `rebuild_diagnostics(perform_rebuild, full_rebuild)` | 只有 `sw_rebuild_model` | **它返回 dirty/失败特征，是一个天然的“判据源”**。**待并入，并升级为通用判据** |
| `inspect_active` | — | 对当前文档做结构自审查。**待并入** |
| `inspect_relations` | — | 检查装配关系/参考完整性。**待并入** |

### D. 证据（1）

| hub 工具 | 我们已有 | 结论 |
|---|---|---|
| `capture_view(output_path, width, height, fit_view, overwrite)` | `sw_screenshot` / `sw_capture_screenshot` | 等价（它们存 BMP）。**不并入** |

### E. 配置（2）

| hub 工具 | 我们已有 | 结论 |
|---|---|---|
| `list_configurations` | `sw_list_configurations` | 等价。**不并入** |
| `create_configuration(name, comment, alternate, activate)` | `sw_add_configuration` | 它的参数更全（备注/别名/激活）。**待并入（扩参）** |
| `activate_configuration` | `sw_activate_configuration` | 等价。**不并入** |

### F. 自定义属性（2）

| hub 工具 | 我们已有 | 差异与结论 |
|---|---|---|
| `get_custom_properties(config)` | `sw_get_custom_properties` | 等价。**不并入** |
| `set_custom_properties(properties, config)` | `sw_set_custom_property`（单条） | 它支持**批量 + 带类型（text/number/bool）+ 指定配置**。**待并入** |

### G. 材料（3）

| hub 工具 | 我们已有 | 结论 |
|---|---|---|
| `list_material_databases` | `sw_list_materials`（直接解析 .sldmat，3 库/474 材料） | 我们的更全。**不并入** |
| `get_material(config)` | `sw_get_material` | 等价。**不并入** |
| `assign_material(db, name, config, rebuild)` | `sw_set_material` | 它可指定数据库与是否重建。**待并入（扩参）** |

### H. 特征图（2）——本轮核心收益

| hub 工具 | 结论 |
|---|---|
| `compile_feature_graph(graph)` | ✅ **已并入** → `sw_feature_graph_compile`（纯函数，判据：步骤数>0、每步有 kind） |
| `execute_feature_graph(graph, out, ...)` | ⏸ **Phase 2**：需要把编译出的 step 映射到 swkit 的现有 API（一个 COM 会话），而不是用它的 executor |

### I. 齿轮 / 轴系 / 整机（6）——本轮核心收益

| hub 工具 | 结论 |
|---|---|
| `create_involute_spur_gear(...)` | ✅ 计划层已并入 → `sw_gear_involute_plan`（判据：d=mz、da=m(z+2)、df=m(z-2.5)、db=d·cosα、特征数>0）；**建模执行留 Phase 2** |
| `create_spur_gear(...)`（梯形近似齿） | 折进同一个 `sw_gear_involute_plan`（它的 `tooth_geometry` 标注是梯形轮廓），**不单独建工具** |
| `create_two_stage_reducer(...)` | ✅ 计划层已并入 → `sw_gearbox_plan`（判据：i=(z2/z1)(z4/z3)、两级中心距 a=m(z1+z2)/2、16 个特征） |
| `create_output_shaft_from_dwg(...)` | ✅ 计划层已并入 → `sw_output_shaft_plan`（判据：总长 333mm、12 个特征、键槽 2 处） |
| `add_stepped_shaft_with_keyway(...)` | ⏸ 参数化零件的 `stepped_shaft` 分支已覆盖大部分；键槽单独补，**Phase 3** |
| `create_parametric_part(part_type, parameters)` | ✅ 已并入 → `sw_part_plan`（block/cylinder/tube/flange/stepped_shaft） |

### J. 特征编辑（7）

| hub 工具 | 我们已有 | 结论 |
|---|---|---|
| `set_dimension` | `sw_set_dimension` | 等价。**不并入** |
| `edit_sketch` | `sw_edit_sketch` | 等价。**不并入** |
| `delete_feature` | `sw_delete_feature` | 等价。**不并入** |
| `set_feature_parameter(name, params)` | — | 按特征名改参数（比“改尺寸”高一档）。**待并入** |
| `rollback(state)` | — | 特征树回滚（退到第 N 个特征），做“分步建模 + 局部验证”的关键。**待并入** |
| `select_references(...)` | — | 显式选参考（面/边/轴）并回读。**待并入** |
| `add_edge_feature(kind, edges, params)` | 有 `sw_fillet/sw_chamfer`（固定两类） | 它支持按边列表 + 通用参数。**待并入（通用化）** |

### K. 其它（2）

| hub 工具 | 结论 |
|---|---|
| `create_sphere` | 用一个旋转草图就能做，**不并入** |
| `health_check`（重复出现） | 见 A |

## 三、值得借鉴的**技术**（不是工具）

这四条与“多一个工具”无关，而是改我自己的内核/适配器：

1. **`request_id` 幂等**：hub 每个工具都带 `request_id`，注释写 "Reusing request_id is safe"。
   我们的内核没有幂等键——重试会重复执行副作用（比如重复切一个孔）。**建议加到 `ToolSpec` 层**。
2. **`operation_status` 非阻塞自省**：我们的单飞锁只能“排队等待”，无法回答“现在忙不忙、排队几个”。
   加一个不进锁的旁路查询，长任务（FEA 15 分钟）时特别有用。
3. **`rebuild_diagnostics` 作为统一判据**：它是“建模后检查 dirty/失败特征”的现成判据源。
   应该做成每个建模类工具的**后置判据**，而不是单独一个工具。
4. **`contracts.py` 的字段级校验风格**：`require_positive` + `ContractError` 带字段名，
   错误信息能直接定位到参数。我们现在的校验还是散在各适配器里。

## 四、本轮已落地（可复现）

```
kitmcp/adapters/hubsw/            # 6 个上游文件原样植入（MIT，未改动）
  contracts.py / involute_gear.py / gearbox.py /
  feature_graph.py / part_generators.py / output_shaft.py
  ATTRIBUTION.md / LICENSE.upstream
kitmcp/adapters/hubsw_tools.py    # 5 个工具 + 数学判据
```

实测（`m=2, z=20, α=20°`）：

```
sw_gear_involute_plan → ok
  pitch_diameter_mm   40.0              OK   (mz)
  outer_diameter_mm   44.0              OK   (m(z+2))
  root_diameter_mm    35.0              OK   (m(z−2.5))
  base_diameter_mm    37.58770483143634 OK   (d·cos20°)
  graph_features      9                 OK

sw_gearbox_plan (20,40)+(20,60) → ok
  total_ratio 6.0 / stage1 2.0 / stage2 3.0
  a1 60.0 / a2 80.0 / 16 个特征          全 OK

sw_output_shaft_plan → ok   总长 333.0mm、12 特征、2 键槽
sw_part_plan(block) → ok    3 特征，编译成 new_part → sketch → boss_extrude
sw_feature_graph_compile → ok（真实图 3 特征 → 3 步）
```

## 五、Phase 2 / 3 的明确前提

**Phase 2（特征图执行、齿轮/减速器建模）前提：**

1. 把 hub 的 `feature_graph` step 语义（`kind` + 参数）映射到 **swkit 的现有工具**，
   而不是引入它的 `executor.py`（那会带第二套 COM 客户端）。
2. 需要读透 `native_features.py`（33 KB）里各 `kind` 对应的 SW API 调用序列。
3. 每个执行类工具都要配 `rebuild_diagnostics` 式后置判据（dirty/失败特征 = 判负）。

**Phase 3（特征树编辑：rollback / set_feature_parameter / select_references / inspect_relations）：**

1. 这些直接对应 `IFeatureManager` / `IModelDoc2` 的 COM 调用，风险低于执行层，可独立做。
2. `rollback` 会改文档状态，必须先存盘/备份（沿用 2026-10-30 的教训：绝不丢弃未保存修改）。

**不建议的路线**：把 hub 的 SW MCP 整体代理进来（40 工具里 20 个重复 + 双 COM 客户端抢同一实例）。

## 六、实施进度（2026-11-02 收尾）

原计划分三阶段，实际**一轮做完**：

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 纯算法（齿轮/减速器/轴/参数化零件/编译） | ✅ 5 个工具，数学判据 |
| Phase 2 | Feature Graph **执行**（新零件里真建模型） | ✅ `sw_execute_feature_graph` |
| Phase 3 | 特征树编辑（inspect/rollback/setparam/select） | ✅ 4 个工具，inspect 已真机验证 |

**关键发现（省掉了原计划的“把 step 映射到 swkit”）**：
上游的 `native_features.execute_plan(model, plan)` 与 `interactive.*` **自己都不建 COM 连接**，
只操作传入的 `model`。所以只要我们自己附加/新建文档，把 model 递进去就能执行——
既不用引入它的 `com_runtime.py`（第二套 COM 客户端），也不用重写 API 映射。

**Phase 2 实测（block 100×60×20）**：

```
sw_execute_feature_graph → ok
  plan_steps              3                 OK
  steps_ok                3/3               OK
  features_added          20                OK   （tail: BlockSketch / BlockBoss）
  body_volume_mm3         119999.99999999999 OK
  volume_matches_expected 119999.99999999999 vs 120000.0  OK
```

**Phase 3 实测**：`sw_feature_inspect` 在真实零件 `0423-1_1.sldprt` 上列出 12 个特征
（注解/曲面实体/实体/光源/方程式/材质/三个基准面…），判据 `features_listed=12`、
`all_features_named=12/12` 全过。测试文档已关闭，`GetDocumentCount` 归 0。

## 七、当前 kit-sw 的四个来源

| 来源 | 工具数 | 说明 |
|---|---|---|
| swkit MCP 代理 | 145 | 建模/装配/出图/钣金/导出 |
| mcp-patches 脚本 | 10 | 分步 FEA / Motion / 扫描 / DocumentMgr 索引 |
| hub 纯算法 | 5 | 齿轮/减速器/轴/参数化零件/编译（不需 SW） |
| hub 交互层 | 5 | 特征树 inspect/rollback/setparam/select + 执行 |
| **合计** | **165** | |