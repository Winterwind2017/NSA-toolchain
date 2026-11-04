# 覆盖率路线图：从 28% 到 100% 的调用覆盖 / 89% 的快乐路径

现状（2026-11-04 13:55 实测，`docs/acceptance-coverage.md`）：

```
工具 609 ｜ 验收 90 ｜ 契约 245 ｜ 合并 289 = 47.5% ｜ 快乐路径 47
未覆盖 320：sw 106 ｜ acad 49 ｜ nx 48 ｜ gx 42 ｜ codesys 39 ｜ ug 32 ｜ autoshop 4
逐 kit：catia 100% ｜ eplan 100% ｜ autoshop 90.5% ｜ ug 61.9% ｜ sw 42.1% ｜ codesys 35.0%
```

三列分开算，**不混报**——这是这份文档的前提。

## 口径

| 列 | 定义 | 上限 |
|---|---|---|
| 验收覆盖 | 验收用例引用到的工具（含「明确拒绝」模式） | 取决于写多少用例 |
| 契约覆盖 | 契约扫描真执行、且返回合统一契约 | **100% 可达** |
| 快乐路径 | 真把功能做对（体积/特征数/编译 0 错/文件头） | **≈89%**（catia 57 + eplan 10 无软件） |

## 为什么现在只有 28.4%

`gated` 436 个，只有四种原因，都写在扫描报告的 `gated` 数组里：

| 原因 | 数量级 | 为什么门禁 |
|---|---|---|
| `app_running` | 少 | 宿主在跑，写探针会真改东西 |
| `app_required` | 多 | 宿主没开，读也会卡在 attach（实测 `acad_projection_orthographic` 卡满 20 s） |
| `write_not_probed` | 最多 | 写类探针可能**把宿主拉起来**（sw 的 COM Dispatch、gx 的 run_capability） |
| `danger` | 12 | 删/停/下载/卸载，永不执行 |

## 到 100% 调用覆盖的两条路

### 路线 A：宿主关闭时开写探针（最快，但要注意拉起）

```powershell
# 先确保这些进程全关：SLDWORKS / acad / CODESYS / AutoShop / GX Works3 / ugraf
python scripts\contract_sweep.py --allow-write-probes --timeout 25 --write
```

写类工具收到的是**故意非法**的参数（`__contract_probe__`），正常情况下会被参数校验挡住；
需要观察的是它们**有没有偷偷把宿主拉起来**（tasklist 里出现新进程就说明这条路线要加
per-kit 黑名单）。这一步能一次吃掉 300+ 个 `write_not_probed`。

### 路线 B：per-kit 沙箱剧本（稳，也是快乐路径的正路）

每个 kit 一条"生命周期剧本"，在隔离环境里把写工具跑一遍：

| kit | 沙箱 | 剧本骨架 |
|---|---|---|
| sw | 新建零件（不保存，跑完关闭） | new_part → sketch → extrude → fillet → pattern → mass → export → close |
| ug | 新建 part | create_part → sketch → extrude → hole → mass → export_step → close |
| nx | nxkit 自拉起 | part_new → sketch_rect → sketch_extrude → measure → export_step |
| acad | 新建 Drawing（不保存） | new → line → circle → dim → table → export dxf → close |
| codesys | 临时工程到 `_runs/sandbox/` | project_create → pou_create → pou_write → task_create → app_generate → export_xml |
| autoshop | 临时 .hcp | new → symbols_add → il_write → check → save |
| gx | 临时 .gx3 | project_new → paste_st → convert → program_check → save → reopen |

剧本用 `_flow()`（`cases.py` 里的多步辅助），一条覆盖 5–15 个工具；
每个 kit 的 `cleanup` 钩子负责删沙箱、关文档。

## 已具备的地基（本轮完成）

| 能力 | 位置 | 状态 |
|---|---|---|
| `expect_error_code` | `harness.evaluate` | ✅ 已用于 eplan 两条用例 |
| `expect_refusal`（ok=False 必须有证据） | `harness.evaluate` + `refusal_evidence` | ✅ |
| `requires` 降级（依赖缺失→拒绝断言，不 SKIP） | `harness.run_kit` | ✅ |
| `cleanup` 钩子（用例级/kit 级，含 TIMEOUT 后） | `harness._run_cleanup` | ✅ 自测 3/3 |
| 多步剧本 `_flow` + `covered_tools` 记账 | `cases.py` / `harness.py` | ✅ nx 两条剧本 2/2 |
| 契约扫描（C0 静态 / C1 真调 / 门禁） | `scripts/contract_sweep.py` | ✅ C0 609/609，C1 154 |
| 两列覆盖率 | `scripts/coverage_report.py` | ✅ |

## 已知契约违规（扫描抓到，待修）

| kit | 工具 | 问题 |
|---|---|---|
| acad | `acad_status` | AutoCAD 没开时返回 `ok=false` 但 `errors` 为空（静默失败），违反统一契约 |

修法：`acad_status` 在未附着时返回 `ok=false` + `reads.error="ACAD_NOT_RUNNING"`，
或在 `errors` 里给一句话。这条是**真问题**——调用方拿不到任何失败原因。

## 本轮踩到的三个边界（都影响"能不能到 100%"）

| kit | 边界 | 结论 |
|---|---|---|
| acad | kit **没有"新建图纸/关闭图纸"工具** | 剧本会画进用户当前图纸 → 不做 acad 快乐路径剧本；要么给 kit 加 new/close，要么用独立 AutoCAD 实例 |
| gx | 写探针必须**已有 GX 会话**，否则每条都在等 UI 拉起（实测 31 条里 29 条 20 s 超时，白烧 10 分钟） | 已加 `HEAVY_WRITE_PROBE_KITS`，默认不发；要跑得加 `--allow-heavy` |
| ug / autoshop | 宿主没运行 → 写工具**快速拒绝**，探针安全 | 已跑：ug 2 → **52**、autoshop 20 → **38** |

另记一条 swkit 的真 bug：`sw_cut_extrude` 在本机 SW2025 上建出**空特征**（体积不变、
features +1），`flip_side` 两种都无效；`sw.flow.fillet` 剧本因此绕开切除。

## NX 与 SW 的结构性差异（影响剧本写法）

* **SW**：一条剧本里多个工具共享同一个文档（create_part → sketch → extrude …），
  能跨步断言体积；所以每条剧本 6–14 步、1–2 分钟。
* **NX**：每条能力**独立开一次 `run_journal` 会话**（实测 13 s/条、各自一个 `_runs/<ts>` 工作目录），
  能力之间不共享文档——`nx_measure_mass` 会自己建块再量。所以 NX 只能写"批量冒烟"
  （`nx.batch.model` 一次跑 10 条），不能用 SW 那种链式剧本。

## 装配剧本为什么没做（实测结论）

`sw_insert_component` 要求**零件预先在同一个 SolidWorks 会话里打开**（否则
`AddComponent5` 返回 None，报 "零件未预先打开时会这样"）。但实测 `sw_create_assembly`
之后文档列表里只剩装配体——零件被关掉了；`sw_open_document` 想重新打开又直接失败。
所以"建零件→存盘→建装配→插组件"这条链在 swkit 当前实现下走不通，
要么改 kit（保持零件打开 / 用 InsertComponent 前显式 OpenDoc6），要么接受装配类工具
只能停在契约覆盖层。
