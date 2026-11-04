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

| 一步到位工具 | 出图特征 | **真机建模实测**（2026-11-04 10:00–10:15，SW 2025 SP4.1） |
|---|---|---|---|
| `sw_create_sphere` | 3 | ✅ Ø40 → **33510.322 mm³**（与解析值 4/3·π·r³ **完全一致**），17.8 s |
| `sw_create_parametric_part` | 3 | ✅ block 40×30×10 → **120000.0 mm³**（精确），9.6 s |
| `sw_create_involute_gear` | 9 | ✅ m2 z20 t10 bore10 → **11474.079 mm³**，22.2 s |
| `sw_create_two_stage_reducer` | 16 | ✅ → **113982.282 mm³**，142.9 s（传动比 6.0、中心距 60/80） |
| `sw_create_output_shaft` | 12 | ✅ → **768065.555 mm³**，26.1 s |

**齿轮为什么是 9 个特征而不是上游的 11 个**：上游最后两步是齿根圆角 + 齿顶倒角，
用的是 `IFeatureManager.FeatureFillet` —— **SW 2025 已经删掉这个成员**，实测报
`com_error (-2147352573, '找不到成员')` 并让整条链失败（那一次跑了 496 s）。
所以 `sw_create_involute_gear` 默认 `include_finishing=false`；要收尾就传 `true`，
但在 SW2025 上那一步仍会失败（swkit 里的正解是走 comtypes 调 14 参 `FeatureFillet3`，
hub 的 `hubsw/native_features.edge_fillet` 还没改过来，见下）。

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

1. ~~SW 一步到位的 `create_*` 封装~~ —— **已做并真机验证**（见 2.1）。
2. ~~`hubsw/native_features.edge_fillet` 用废弃 API~~ —— **已修**，见下面的
   「SW2025 API 变更与适配」。收尾圆角现在能建出特征（实测特征名 `ProbeFillet`），
   但因为边枚举慢，`sw_create_involute_gear` 的 `include_finishing` 仍默认 `false`。

## 五、SW2025 API 变更与适配（2026-11-04 实测）

在 SolidWorks Premium 2025 SP4.1（`RevisionNumber 33.4.1`）上，上游 vendored 代码里有
**三处** pywin32 调用已经不成立，我把它们逐个换掉了：

| 原调用 | 症状 | 现方案 |
|---|---|---|
| `edge.GetStartVertex()` / `GetEndVertex()` | `com_error(-2147352573, '找不到成员')` | 退到 `edge.GetCurveParams2()`，返回的前 6 个数就是起点 + 终点（米） |
| `SelectionManager.CreateSelectData()` | 同上（成员解析不到） | 用 comtypes `ISelectionMgr.CreateSelectData()` 造 `ISelectData`，再 `pythoncom.WrapObject(..., IID_IDispatch, IID_IDispatch)` 桥回 pywin32，`edge.Select4(True, bridged)` 实测返回 `True` |
| `FeatureManager.FeatureFillet(195, r, 0,0, None,None,None)` | 同上 | comtypes 14 参 `FeatureFillet3(2, r, 0,0, 0,0,0, None×7)`（swkit 同款），边必须先选中 |

细节坑（都试过才定下来）：
* `doc.SelectionManager` 在 comtypes 里是 `_Dispatch`，`CreateSelectData` 会被当成属性
  → 必须 `QueryInterface(module.ISelectionMgr)` 才有方法；
* `GetBodies2` 在 **`IPartDoc`** 上，不在 `IModelDoc2`；而 comtypes 调
  `IPartDoc.GetBodies2` 会因 `VT_DISPATCH` 数组（vt=9）抛 `KeyError` →
  所以「拿边」仍走 pywin32，只有「选边 / 建圆角」走 comtypes。

**性能现实**：`GetCurveParams2` 一次约 **0.24 s**（实测 879 条边用 211.5 s）。
所以齿轮这种上千边的模型，带收尾要多花 **3–4 分钟**；`include_finishing` 默认关，
需要时显式传 `true`。选择器已支持 `max_edges` 早停。
2. **EPLAN 真机读工程**：本机只装了 License Client，**没有平台本体**（`Eplan.exe`
   不存在），所以 `eplan_bridge_discover` 恒为 `[]`。要读真实工程得先装
   EPLAN Platform 2.9，再按 `docs/eplan-bridge-handoff.md` 四步接桥；
   上机前先跑 `python scripts\eplan_preflight.py` 看卡在哪一环。
3. **上游后续提交**：已有 `scripts/sync_upstream.py` 处理——
   `--check` 报差异、`--verify` 验补丁重放等价、`--regen-patches` 重生成补丁、
   `--apply --yes` 备份后真同步并编译。用法与三条硬规则见 `docs/upstream-sync.md`。
4. **上游测试对照**：`tests/parity/run_parity.py` 跑三组上游测试，实测
   **145 通过 / 0 失败**（hubsw 18 + EPLAN 68 + CATIA 59），见 `docs/parity-tests.md`。
   没搬的部分（要真机/编译器/上游 server 进程）逐条写了原因。
   覆盖率由 `scripts/coverage_report.py` 三列统计：**验收 50 ｜ 契约 154 ｜
   合并 173 = 28.4% ｜ 快乐路径 8**（`docs/acceptance-coverage.md`）。
   提升路线（到 100% 调用覆盖 / 89% 快乐路径）见 `docs/coverage-plan.md`；
   契约扫描还抓到一处真问题：`acad_status` 未附着时 ok=false 但错误为空。
