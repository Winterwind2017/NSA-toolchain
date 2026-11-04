# 覆盖率路线图：从 28% 到 100% 的调用覆盖 / 89% 的快乐路径

现状（2026-11-04 16:32 实测，`docs/acceptance-coverage.md`）：

```
工具 611 ｜ 验收 275 ｜ 契约 245 ｜ 合并 448 = 73.3% ｜ 快乐路径 238
未覆盖 163：sw 73 ｜ gx 40 ｜ ug 32 ｜ codesys 10 ｜ autoshop 4 ｜ nx 2 ｜ acad 2
逐 kit：catia 100% ｜ eplan 100% ｜ nx 97.0% ｜ acad 96.4% ｜ autoshop 90.5% ｜ codesys 83.3% ｜ ug 61.9% ｜ sw 60.1% ｜ gx 14.9%
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

## CODESYS 剧本：打通了（2026-11-04 15:30 实测）

原先卡住的不是权限而是**工程内容**：当时打开的临时工程没有 device / application
（`E_STATE: no active application`）。用 `project.create` 带上
`device="CODESYS Control Win V3"` 建**带 device 的新工程**后一切正常，
两条剧本合计 **3.9 s** 跑完（CODESYS 是最快的 kit，不是最慢的）：

| 剧本 | 步数 | 覆盖 |
|---|---|---|
| `codesys.flow.pou` | 8 | project.create / pou.create / pou.write×2 / pou.read / app.generate / app.status / export.xml |
| `codesys.flow.ops` | 11 | tasks / task.create / folder.create / object.rename / object.info / project.meta / libs / find.text / save / save_as / archive |

三个必记的坑：

1. **POU 路径必须写全路径** `/PLC/Plc Logic/Application/<名字>`，写 `/AcPlay` 会
   `E_STATE: path segment not found`（而且 `pou_create` 仍然返回 ok）。
2. **读数都在 `reads.result` 里**（`result.text` / `result.is_uptodate`），
   顶层 `reads.text` 是空的——我第一版就是这么写错的。
3. `codesys_symbols_create` 实测 `E_SCRIPT: 父对象不接受符号配置对象`，
   不传 parent 建不出来，已从剧本移除。
4. 安全门禁：`codesys_setup` 会先查当前工程路径，**只有没有工程或工程在临时目录**才跑剧本
   （`project.create` 会 `closed_previous: true`，绝不能关你的工程）。

## SW 的"能批量"与"不能批量"（这轮实测划清）

| 类别 | 能否同会话连续调 | 证据 |
|---|---|---|
| 只读轻工具（状态/注册表/索引/包围盒/模型信息） | **能** | 夹具（几百特征）打开时 12 个工具 0–11 s 全过 → `sw.light.reads` |
| 建文档 + 改几何的链式剧本 | **能** | 9 条剧本每条 30–100 s 全过 |
| 同会话里"建/关多个文档"的批量 | **不能** | 上轮 600 s 卡死；疑似 CloseDoc 触发模态对话框 |

## 本轮又抓到两个"返回值骗人"的坑

| kit | 工具 | 现象 | 处理 |
|---|---|---|---|
| sw | `sw_export_iges` | 传 `p.iges` 会**归一成 `p.igs`**，按传入路径查文件永远 0 字节（工具本身 ok、写了 22 KB） | 判据改用 `reads.path` 返回的实际路径 |
| codesys | `pou.member` / `project.io_export` | `E_SCRIPT 名称'Calc'对此对象无效` / `E_STATE path segment 'CODESYS Control Win V3' not found`（device 参数要的是树路径不是设备名） | 两个都没纳入剧本，记在这里 |

## SW 在验收上下文里会卡死的三类组合（2026-11-04 实测，累计三条）

| 组合 | 现象 | 结论 |
|---|---|---|
| 同会话里批量"建/关多个文档" | 600 s 超时 | 已废弃批量用例 |
| `sw_scale_body` 紧跟 `sw_create_reference_axis` | >10 min 不返回 | 拆开后「只缩放+另存」仍卡 → 整个 misc 剧本撤掉 |
| 带构造线时 `sw_exit_sketch` | 返回 `ok=false`，reads 里 `segments_after=1` | 判据（segments 变化）误判，不是几何问题 → 剧本不 exit |

另记一处**静默失败**：`sw_sketch_text` 返回 `ok=false` 且 `errors` 为空（第 3 个此类违规，
前两个是 `acad_status`、`sw_zoom_to_fit`）。

## acad 为什么卡了 8 轮、这轮怎么解开的（2026-11-04）

原来 acad 不是"做不了"，而是**缺两个基础工具**：kit 里没有"新建图纸/关闭图纸"，
于是任何剧本都会画进用户当前图纸、也没法安全收尾。这一轮给 acadkit 补了
`doc.new` / `doc.close` 两条真机能力（自带判据与自清理），
再用它们把 51 个生成工具分 8 批跑通：acad 4 → **53 / 55（96.4%）**。

### 一个必须记住的危险动作

`acad_boolean_section_slice`（SLICE）实测会**超过 case_timeout**，acadkit 的看门狗
随即 `taskkill /F /IM acad.exe` —— 2026-11-04 16:14 真的把用户的 AutoCAD 强杀了一次
（当时开着 3 个未保存图纸）。结论：

* 该能力**不进验收**；
* acadkit 的看门狗是"宁可杀 CAD 也不挂住"，跑 acad 批量时要意识到这个代价；
* 事后处理：删掉 `%TEMP%\*.sv$`、用 `acadkit.core.launch.launch()` 重新拉起
  （它会强制 `<<VANILLA>>`），再确认 `CPROFILE=<<VANILLA>>`。

## CODESYS 在线链路的必要条件（2026-11-04 实测）

`online.state` 报 `E_SCRIPT: 无法获取 IOnlineApplication 实例` 不是权限问题，而是
**工程里还没有 application 实例**。顺序必须是：

```
project.create → pou.create → app.generate → online.simulation(True)
→ online.login(autostart=True) → online.state → online.read → online.logout
```

开仿真后 `online.login` 不需要真 PLC，整条链 5.9 s（17 步剧本）。另记一处静默失败：
`textlist.export` 返回 ok=False 且 errors 为空，但 CSV 确实写出来了（224 B）。

## gx 的"快/慢"分界（2026-11-04 实测）

| 工具 | 耗时 | 说明 |
|---|---|---|
| `gx_list_caps` / `gx_selftest` / `gx_status` | **0 s** | 纯离线，不碰 GX Works3 |
| `gx_inspect_devices` / `gx_inspect_devices_rcpu` | **114 s** | 要拉起 GX Works3 读设备模板 |
| 其余（build/program/label…） | 57–595 s | 建工程或画梯形图，且会抢焦点 |

一条 `gx.batch.offline`（5 条，172 s）把 gx 从 10.6% 拉到 14.9%；
再往上就只能接受"每 5–6 个工具花 10 分钟且 GX 会被打开"。

## 剩余未覆盖逐类归因（2026-11-04 定稿）

`docs/acceptance-coverage.md` 里"未覆盖"是**并集口径**（验收 ∪ 契约都没跑过）。
按原因分四类，其中只有第 1 类是真能再吃的：

### 1) 时间成本型（能覆盖，只是慢）—— gx 41 个
全部是 `build.*` / `program.*` / `label.*` / `datatype.*` / `project.*` 家族，
单条 57–595 s（`write_ladder` 595 s、`import_fb` 434 s），且每条都要拉起 GX Works3 抢焦点。
把 41 条跑完约 2–3 小时。**不是不能，是不划算**；需要时用
`python -m nsa_mcp_hub.acceptance --kit gx` 单独跑。

### 2) 环境不具备型 —— ug 32 个（全部）、autoshop 4 个
ug 的 32 个都是 `app_required`：kit 要求 **NX 里装入 `NXMcPRemotingServer.dll`
（在 NX 里按 Ctrl+U 加载）**，否则 `ug_ping` 直接报

```
cannot reach the non-blocking NX bridge at http://127.0.0.1:48161/NXOpenSession;
load NXMcPRemotingServer.dll in NX with Ctrl+U
```

这是**NX 内的手工步骤**，脚本无法代劳 —— 所以 ug 停在 61.9%（52/84 靠"宿主缺失时快速拒绝"吃到）。
autoshop 剩下的 4 个是 `danger`（永不执行）。AutoShop 宿主没开时另外 33 个是
`app_required`，已在契约层用写探针覆盖（38/42）。

### 3) kit 自身缺陷型 —— sw 装配族、codesys 若干
| 现象 | 工具 | 结论 |
|---|---|---|
| 要零件**预先在 SW 会话里打开**才插得进去；`create_assembly` 之后文档列表只剩装配体、`sw_open_document` 又失败 | `sw_insert_component` / `create_assembly` / 组件族 12 个 | 要改 swkit（保持零件打开），现在做不了 |
| `ok=false` 且 `errors` 为空（静默失败） | `sw_sketch_text` / `sw_add_datum_feature` / `sw_add_gtol` / `sw_add_weld_symbol` / `textlist.export` | kit 缺陷，判据拿不到原因 |
| 工具自身直接报错 | `codesys_symbols_create`(E_SCRIPT 父对象不接受) / `import_xml`(未找到可导入对象) / `object_move`(index 必须 -1) / `project_open`(文件被本会话占用) / `pou_member`(名称无效) | kit 缺陷，需修 |

### 4) 主动不测型（危险）—— acad 2、nx 2、sw 仿真/删改 ~15
| 工具 | 原因 |
|---|---|
| `acad_boolean_section_slice` | 超时触发 acadkit 看门狗 `taskkill /F /IM acad.exe`，**真杀过用户的 CAD 一次** |
| `nx_solid_delete_face` | 删面愈合，会破坏模型 |
| `sw_delete_body` / `delete_feature` / `delete_equation` / `sim_solve`… | 删改不可逆；FEA 单次 15 分钟 |
| `kit_runtime` | 内部工具，不是业务能力 |

### 天花板结论

* **100% 不可达**，原因不在测试写得不够，而在上面三类硬约束；
* 当前 73.3%（448/611）里，**除第 1 类外能吃的已经吃完**；
* 若要继续，性价比排序是：gx（时间）→ 修 swkit 装配（代码）→ 装 NX bridge（环境）。

## 全量回归的实测结论（2026-11-04 17:00 收尾轮）

跑 `python -m nsa_mcp_hub.acceptance --report _runs/acceptance-full-regression.json`
（全部 kit / 全部用例）时出现一个必须写下来的现象：

```
PASS  sw.inspect.topology   69 s
PASS  sw.param.thickness      3.6 s
PASS  sw.flow.part           33 s
PASS  sw.flow.fillet         66 s
TIMEOUT sw.flow.inspect     600 s   ← 单条用例超过 600 s，已放弃并重启该 kit 服务器
```

* `sw.flow.inspect` **单跑 66 s 通过**（本轮早前实测），在长会话里 600 s 超时；
* 同一条链路上另外两条（`sw.flow.part`/`fillet`）也正常，说明不是代码坏了，
  而是 **SW 的 COM 会话在连续跑十几条用例后会退化**（与第 4 轮"同会话批量卡死"同源）；
* 所以全量回归**不适合一条命令跑完 SW 全部 39 条**：建议按 kit 分批
  （`--kit sw --only <组>`），这也正是本文件里各条剧本的验证方式。

这条不是"覆盖率造假"，而是**验收执行方式的边界**，记在这里避免下次误判成回归。
