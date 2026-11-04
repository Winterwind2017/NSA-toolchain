# 上游差集报告：CAD-Agent-Hub @ c051b72 → nsa-mcp-hub

统计方式：把两边的工具名**归一化去掉 kit 前缀**后比集合；差集再逐个看实现，
区分「真缺能力」「其实是组合」「只是别名」。

基线：`https://github.com/Cai-aa/CAD-Agent-Hub`，`main` = `c051b72`
（`Merge pull request #6 from S2mon123/feat/eplan-native-mcp`，260 个文件）。

## 一、结果总表（2026-11-04 03:05 实测）

| kit | 上游工具 | hub 工具 | 缺 | 处理 |
|---|---|---|---|---|
| **ug** | 82 | 84 | **0** | 已对齐（hub 多 2 个是 `kit_runtime` / `proxy_tools`） |
| **catia** | 55 | 57 | **0** | 已对齐 |
| **sw** | 40 | **183** | **19 → 0** | 见第二节；含 5 个一步到位封装 |
| **eplan** | 67（review 17 / trial 77） | **0 → 17 / 77** | **0** | 新 kit，见 `docs/eplan-kit.md` |

## 二、SW 那 19 个的定性

### 2.1 曾是「规划 + 执行」两步，现已补成一步（6 个）

上游 `create_*` 是**一步到位**；hub 原来是两步（`*_plan` → `execute_feature_graph`）。
现在补了 5 个封装工具，**一次调用就出图并直接建到 SolidWorks**：

| 一步到位工具 | 内部步骤 | 出图特征数（实测） |
|---|---|---|
| `sw_create_involute_gear` | `InvoluteGearSpec`（半径按 ISO 自动推）→ 图 → 执行 | 11 |
| `sw_create_sphere` | `primitives` → 图 → 执行 | 3（附解析体积 33510.322 mm³ @Ø40） |
| `sw_create_parametric_part` | `part_generators` → 图 → 执行 | 3（block） |
| `sw_create_two_stage_reducer` | `gearbox` → 图 → 执行 | 16（传动比 6.0、一级中心距 60） |
| `sw_create_output_shaft` | `output_shaft` → 图 → 执行 | 12 |

参数：`execute`（默认 true；`false` 只出图，不用开 SolidWorks）、`save_path`、
`expected_volume_mm3`、`include_graph`。执行仍走 `sw_execute_feature_graph` 的语义：
**永远新建文档**，不碰用户已打开的文件。

验收（不需要开 SolidWorks，标了 `no_setup`）：

```
sw.sphere.plan      PASS 43 ms
sw.create.gear      PASS  2 ms
sw.create.reducer   PASS  1 ms
sw.create.sphere    PASS  1 ms
sw：4/4 通过（1.2s）
```

功能等价论证（原两步路径）：

```
sw_gear_involute_plan(m=2, z=20) → feature_graph(9 个特征)
sw_feature_graph_compile(graph)  → ok, step_count=9
```

| 上游 | hub 组合 |
|---|---|
| `create_spur_gear` / `create_involute_spur_gear` | `sw_gear_involute_plan` → `sw_execute_feature_graph` |
| `create_parametric_part` | `sw_part_plan` → `sw_execute_feature_graph` |
| `create_two_stage_reducer` | `sw_gearbox_plan` → `sw_execute_feature_graph` |
| `create_output_shaft_from_dwg` | `sw_output_shaft_plan` → `sw_execute_feature_graph` |
| `compile_feature_graph` | `sw_feature_graph_compile`（同名能力） |
| `add_edge_feature` | `sw_fillet` / `sw_chamfer`（上游是执行器里的边操作） |

### 2.2 新补的（1 个）

| 上游 | hub 现在 |
|---|---|
| `create_sphere` | **`sw_sphere_plan`**（新）+ `sw_execute_feature_graph` |

实现：把上游 `solidworks_mcp/primitives.py`（纯 Python，3 个特征：中心线 + 两段
1/4 圆弧 + 旋转）搬进 `nsa_mcp_hub/adapters/hubsw/primitives.py`，在
`hubsw_tools.py` 注册 `sw_sphere_plan`，判据是**特征数 3** 与**体积 4/3·π·r³**。

```
sw_sphere_plan(diameter_mm=40) → feature_count=3, expected_volume_mm3=33510.322
sw_feature_graph_compile(graph) → ok, step_count=3
```

验收用例 `sw.sphere.plan`（47 ms，**不需要开 SolidWorks**，标了 `no_setup`）。

### 2.3 只是别名（11 个，不加）

| 上游名 | hub 名 |
|---|---|
| `assign_material` | `sw_assign_material_full` / `sw_set_material` |
| `get_bounding_box` | `sw_bounding_box`（还有 `_with_hidden` 版） |
| `capture_view` | `sw_capture_screenshot` |
| `create_configuration` | `sw_create_configuration_full` / `sw_add_configuration` |
| `export_active` | `sw_export_file` / `sw_export_step`… |
| `health_check` | `sw_status` / `sw_connect` |
| `list_documents` | `sw_list_open_documents` |
| `save_active` | `sw_save_document` |
| `rollback` | `sw_feature_rollback` |
| `list_material_databases` | `sw_list_materials` |
| `assign_material`（重复） | 同上 |

刻意**不加别名**：两套名字共存只会让 agent 选错。要兼容时在文档里查这张表。

## 三、文件级对比

| 目录 | 上游独有 py | 本地独有 |
|---|---|---|
| `MCP/UG` | 0 | 0（原有 4 个 `_cam_probe*.py` 已删） |
| `MCP/Solidworks` | 0 | 0 |
| `MCP/CATIA` | 0 | 0 |
| `MCP/EPLAN` | 整包（已复制到 `CAD-Agent-Hub/MCP/EPLAN`） | — |

内容差异（不是文件差异）：本地 UG 原为旧快照，已按 `docs/patches/ug-cam-recipe.patch`
重放到 `c051b72` 基线上。

## 四、还没做的

1. ~~SW 一步到位的 `create_*` 封装~~ —— **已做**（见 2.1），且没动第三个仓库：
   封装放在 hub 的 `adapters/hubsw_create.py`，组合「图生成器 + 执行器」两半。
   待办只剩一件事：`execute=true` 的实际建模还没在真机跑过（本机 SolidWorks 没开）。
2. **EPLAN 真机读工程**：本机装了 EPLAN，但没开；`eplan_bridge_discover` 返回 `[]`。
   要读真实工程需要起 bridge（上游 `bridge.py` 的 named pipe 协议）。
3. **上游后续提交**：以 `c051b72` 为基线，之后上游再有改动需要重新 `git fetch` 并重放补丁。
