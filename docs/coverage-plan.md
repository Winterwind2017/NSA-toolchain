# 覆盖率路线图：从 28% 到 100% 的调用覆盖 / 89% 的快乐路径

现状（2026-11-05 11:00 实测，`docs/acceptance-coverage.md`）：

```
工具 618 ｜ 验收 422 ｜ 契约 245 ｜ 合并 558 = 90.3% ｜ 快乐路径 386
未覆盖 60：sw 37 ｜ ug 13 ｜ autoshop 4 ｜ codesys 2 ｜ nx 2 ｜ acad 2
逐 kit：catia 100% ｜ eplan 100% ｜ gx 100% ｜ codesys 96.7% ｜ nx 97.0% ｜
        acad 96.4% ｜ autoshop 90.5% ｜ ug 84.5% ｜ sw 80.5%
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

## 修掉的两个真 bug（2026-11-04 收尾轮，用户要求「继续修」）

### ① swkit 的 `AddComponent5` 少了参数（装配链全废的根因）

```python
# swkit/api/app.py 现状（错的）
doc.AddComponent5(file_path, 0, "", fixed, x, y, z)      # 7 个参数
# IAssemblyDoc::AddComponent5 实际是 8 个：
AddComponent5(CompConfig, UseConfigForPart, NewPartPath, ConfigOption, InsertedOption, X, Y, Z)
```

少一个 → 晚绑定报「非选择性的参数」→ 返回 None → 所有装配相关工具都只看到
`components_after = 0` + "backend error"。**这就是 sw 装配族 12 个工具一直覆盖不了的根因。**

hub 侧修法（不改上游）：新增 `nsa_mcp_hub/adapters/hubsw_asm.py`，直接在本进程用 COM，
按实测的三个必要顺序执行 —— **打开零件 → `ActivateDoc3` 把装配体切回活动 → 8 参插入**，
判据用 `GetComponents` 数读回。新增两个工具：

| 工具 | 判据 | 真机 |
|---|---|---|
| `sw_assembly_build` | parts_inserted = N、component_count = N | 2/2、组件 p-1/p-2 ✅ |
| `sw_assembly_add` | 同上（往已有装配体追加） | 未单独跑 |

新验收用例 `sw.flow.assembly`（14 步：建件→建装配→插两件→干涉 0→读树→固定→
显示全部→抑制/解抑制→爆炸）**真机 43.5 s PASS**，顺带覆盖
`sw_check_interference` / `sw_get_assembly_tree` / `sw_fix_component` /
`sw_show_all_components` / `sw_suppress_component` / `sw_explode_assembly`。

### ② 静默失败（ok=false 但 errors 为空）

根因不在工具，而在内核收口：`normalize()` / `apply_checks()` 只把 `ok` 算成
`all(checks) and not errors`，**判据失败时不会补 errors**，于是
`sw_zoom_to_fit` / `sw_add_gtol` / `acad_status` 这类返回 `ok=false, errors=[]`。

修法（`nsa_mcp_hub/tools.py`，两处同一套规则）：ok 掉下来却没有 errors 时，
按失败判据自动补一条可读原因。实测效果：

```
修前：sw_zoom_to_fit ok=False errors=[]
修后：sw_zoom_to_fit ok=False errors=["判据未通过：scale_changed"]
```

### 顺带确认的两条边界

* `sw_add_hole_table` 在装配图上**会卡死**（>10 min），不纳入；
* 装配体出图整条链在验收长会话里 900 s 超时（单客户端直跑是通的），
  用例已删、函数保留并注明「未纳入验收」—— 与 SW COM 会话退化同源。

## 用户要求「继续修」之后新增的四条剧本（2026-11-04 19:20–19:40）

| 用例 | 步数 | 真机 | 覆盖到的新工具 |
|---|---|---|---|
| `sw.flow.asm_ops` | 16 | 40.7 s | 引用文档/显示状态/配置/建 CFG2/材质/自定义属性/组件阵列/组件镜像 |
| `sw.batch.misc` | 14 | 47 s | connect / api / clear_selection / select_entity / start_3d_sketch / save_as_copy / save_all / activate_document / reload_runtime |
| `sw.flow.revolve` | 12 | 49.9 s | revolve（体积 35342.917 mm³ 与 π·30·(20²−5²) 吻合）/ revolved_surface |
| `sw.flow.dwgviews` | 9 | 36.4 s | add_drawing_view / add_auxiliary_view |

**再确认三条不能用的**（都已排除）：`sw_move_component` 卡死（>9 min）、
`sw_assign_material_full` 在装配体上判据不过、`sw_scan` 在 cmd_scan 里 getsize 抛错。

## 选择类工具：解锁"必须先选中"的那批 sw 工具（2026-11-04 21:00）

之前把「草图圆角/倒角/剪裁/转换实体/圆周阵列、特征阵列/镜像」记成 kit 缺陷，
其实是**缺一层选择能力**：swkit 这些工具内部不自己选，而它没有"按名字/序号选中"的工具。

hub 侧新增（`nsa_mcp_hub/adapters/hubsw_select.py`，直接 COM）：

| 工具 | 判据 | 实测 |
|---|---|---|
| `sw_select_sketch_segments(indices, append)` | SelectionManager 选中数 = 期望 | 2 条线 → selected_count=2 ✅ |
| `sw_select_features(names, append)` | 同上 | 按名字选特征（BODYFEATURE/SKETCH 都试） |

**验证结论**（真机）：

* 选中 2 条线 → `sw_sketch_fillet(5)` 成功，segments 2→3；
* 选中 1 条线 → `sw_sketch_trim` 成功；
* 仍然不行：`sw_sketch_chamfer`（segment_added=False）、`sw_sketch_convert_entities`、
  `sw_sketch_circular_pattern`（这两个要模型边/中心点，不是草图线段）。

新用例 `sw.flow.sketch_ops`（9 步，真机 24 s）PASS。

## gx 的六条剧本（2026-11-04 21:00 起跑）

gx 40 个未覆盖工具全是时间成本（单条 57–595 s），所以按能力族拆成 6 条剧本，
每条自带工程上下文、失败即停：

| 用例 | 步数 | 覆盖 |
|---|---|---|
| `gx.flow.project` | 7 | 四种工程创建 + 保存/元信息/重开（实测 **924 s** PASS）|
| `gx.flow.program` | 7 | ST 粘贴/读回 + 梯级/并联/应用指令 |
| `gx.flow.build` | 7 | 全部转换 + 程序检查 + 编译诊断/定位坏行 |
| `gx.flow.inspect` | 7 | 读程序/梯形图/IL/源码映射 |
| `gx.flow.label` | 8 | 标签多类型 + 结构体成员/数组/XML 导入 |
| `gx.flow.xml` | 7 | XML 建程序/功能块/实例 + 多程序 + 批量工程 |

### gx 六条剧本实测（2026-11-04 21:06–23:03，共 7021 s）

```
PASS gx.flow.program   1580 s
PASS gx.flow.build     1145 s
PASS gx.flow.inspect   1046 s
PASS gx.flow.label     1457 s
PASS gx.flow.xml       1622 s
PASS gx.batch.offline   170 s
6/6 通过（7021 s）+ gx.flow.project 924 s
```

结果：gx 14.9% → **89.4%**（42/47），只剩 5 个未覆盖
（`batch_new_projects` / `program_read_st` / `program_fb_params` / `project_check` /
`project_diff` 之外的内部项）。

### gx 收尾（2026-11-04 23:50）

`gx.flow.tail`（工程校验 / 工程比对 / 批量建工程 / 功能块带参数 / iQ-R 往返，6 步）
**PASS 1396.8 s** → **gx 47/47 = 100%**（快乐路径 45）。

### sw 钣金（2026-11-05 00:00）

`sw.flow.sheet`（选面 → `insert_bends` → 展开信息 → 选边 → 圆角，10 步）
**PASS 139 s** —— 靠新加的 `sw_select_faces` / `sw_select_edges` 才走得通。
实测 `sw_hem` 判据不过（`feature_added=False`），仍不纳入。

### sw 再吃三条（2026-11-05 00:05–00:12）

| 用例 | 步数 | 真机 | 新覆盖 |
|---|---|---|---|
| `sw.flow.artifacts` | 10 | 42.8 s | `export_file`(PDF 172 KB) / `screenshot`(BMP 1.4 MB) / `capture_screenshot`(PNG) / `unsuppress_feature` |
| `sw.flow.assemble` | 12 | 147.6 s | `edit_sketch` / `split_line`(96.5 s) / `create_assembly` / `open_document` / `assembly_add` |

### sw 剩 42 个：按原因分类（这是真实天花板）

| 类型 | 数量 | 例子与原因 |
|---|---|---|
| 需要"选中模型边/面并投影" | 4 | `sketch_convert_entities` / `sketch_circular_pattern` / `sketch_text` / `sketch_chamfer` —— 都要在**面草图**里选边，swkit 的 `create_sketch` 只接受基准面名 |
| FEA / Motion | 7 | `sim_setup/mesh/run/read/faces`（单次 15 分钟）、`motion_list/read`（要运动算例） |
| 出图细节要预选 | 8 | `add_gtol/datum/weld/center_mark`（要先选尺寸/面）、`add_bom_table`/`add_hole_table`（要装配图且 hole_table 会卡死）、`add_broken_view`/`create_section_view`（要选视图/剖面线） |
| 删改/变换要选实体 | 8 | `delete_body`/`delete_equation`/`move_body`/`scale_body`/`mirror`/`combine_bodies`/`suppress_feature`/`pattern_feature` —— `suppress_feature` 实测 `suppressed=False`（名字对也不生效） |
| 尺寸对象 | 3 | `get_dimension`/`set_dimension`/`measure_distance` —— 直接 backend error（要 3D 尺寸注释对象） |
| 关文档 | 2 | `close_all`/`close_document` —— 会关用户的文档，主动不测 |
| kit 自身判据不过 | 6 | `assign_material_full`(装配体上 assigned=False)、`activate_configuration`(activated=False)、`inspect_relations`、`replace_component`、`hide_component`、`create_parametric_part`/`create_output_shaft`(executed/saved=False) |
| 其它 | 4 | `analyze_draft`(要分型线)、`flow_check`(要 Flow 插件)、`scan`(cmd_scan 抛错)、`vba_dump`(要 .swp) |

### sw 最后一轮短剧本（2026-11-05 00:15–00:40）

| 用例 | 步数 | 真机 | 新覆盖 |
|---|---|---|---|
| `sw.flow.modify` | 8 | 63.6 s | `suppress_feature` / `unsuppress_feature` / `delete_feature`（**中文特征名直传可用**）|
| `sw.flow.delete_body` | 6 | 36.8 s | `delete_body` |
| `sw.flow.bodies` | 9 | 89.9 s | `move_body` / `scale_body` / `mirror` / `combine_bodies` |

另外两条实测结论（都已排除）：

* `sw_sim_setup` 单客户端直跑 **9.8 s 通过**（关键前提：**先赋材质**，否则报"该零件没有材质"，
  RunAnalysis 返回 19），但在验收会话里 900 s 超时 —— 用例删掉、函数保留；
* `sw_select_features` 对中文特征名**仍然选不中**（`SelectByID2` 与特征树遍历两种都试过），
  但 `suppress_feature` / `delete_feature` 不需要选中就能用，所以这批不影响覆盖。

## NX（ug）桥起来了：UGII_USER_DIR 指到 nx_user 就会自动加载 DLL（2026-11-05 09:55）

之前把 ug 记成"环境阻塞、要人手 Ctrl+U"，**这是错的**：

```
$env:UGII_USER_DIR = 'D:\bililive\CAD-Agent-Hub\MCP\UG\nx_user'
Start-Process 'D:\Program Files\Siemens\DesigncenterNX2512\NXBIN\ugraf.exe'
→ 45 秒后 127.0.0.1:48161 就在听，ug_ping ok
```

`nx_user\startup\NXMcPRemotingServer.dll` 是 NX 启动时自动加载的（NX 的 standard
startup 机制），**根本不需要 Ctrl+U**。起来之后 ug 工具都在 0.4–15 s。

新增 4 条剧本（全部 PASS，合计 30.7 s）：

| 用例 | 覆盖 |
|---|---|
| `ug.flow.model` | create_part / create_block / inspect_body_topology / get_part_summary / inspect_work_part_geometry / rebuild_work_part / run_python / save_work_part / export_exchange / import_exchange |
| `ug.flow.cam` | initialize_cam_setup / get_cam_capabilities / create_cam_milling_context / define_cam_mcs / define_cam_workpiece / create_cam_mill_tool / create_cam_operation / set_cam_operation_geometry / inspect_cam_operations / inspect_cam_setup |
| `ug.flow.drawing` | create_drawing_sheet / create_projected_view / create_drafting_note / inspect_drawing_annotations |
| `ug.flow.sheetmetal` | create_parametric_sketch / inspect_sketch / create_sheet_metal_tab / inspect_work_part_geometry |

**踩到的参数坑**：`create_part` 的文件名重名会报"文件已存在"（每次用 uuid 后缀）；
`view_position`/`note.position` 要**三个**坐标、`rectangle.origin` 要**两个**；
`create_cam_operation` 的 `tool_name` 必须等于已建的刀具名（默认 `T01_END_MILL`）；
`generate_cam_toolpath` 目前 backend error（几何没选对，CLSF 导出因此也不可用）。

### ug 再来两条（2026-11-05 10:00）

| 用例 | 真机 | 新覆盖 |
|---|---|---|
| `ug.flow.modeling2` | 4.8 s | `extrude_sketch` / `create_cylindrical_hole` / `fillet_edges` / `chamfer_edges` / `extract_face_surface` / `offset_surface` / `create_involute_gear` / `inspect_feature` / `proxy_tools` |
| `ug.flow.features` | 2.8 s | `linear_pattern_feature` / `mirror_feature` / `inspect_assembly` / `inspect_assembly_constraints` |

**ug 剩下的 15 个是"有前置条件的模块"**：机床/运动学（要 machine profile 文件）、
CAM 刀路（`generate_cam_toolpath` backend error）、装配写入（`add_component` 要真正的
装配上下文）、钣金弯边/展开（几何相关：`边必须切向连续`、`该面不是有效的钣金面`）、
`revolve_sketch`（矩形+轴线不是有效回转剖面）、`shell_body`/`boolean_bodies`（要多实体）、
`set_feature_expression`（要已命名的表达式）。

### CODESYS 的三个残留（全是 kit 自身缺陷，不是没测）

* `online_write` —— 任何表达式都回"无效的表达式"（`AccW.x` / `Application.AccW.x` /
  `PLC_PRG.x` 全试过）；顺带发现 `online_read` 会把 `"error: 无效的表达式"`
  **当成功返回**（判据只看 ok，不看 value）——这是个静默失败，值得改 kit。
* `textlist_export` —— `ScriptObject` 没有 `export` 属性（脚本 API 用错）。
* `symbols_create` 在部分工程类型上"父对象不接受符号配置对象"。

### ug 剩 15 个：都要前置模块或专门几何

机床/运动学（要 machine profile 文件）、`generate_cam_toolpath`（backend error，
连带 CLSF 导出不可用）、`add_component`（要真装配上下文）、钣金弯边/展开
（`边必须切向连续` / `该面不是有效的钣金面`，几何相关）、`revolve_sketch`
（矩形+轴线不是有效回转剖面）、`shell_body`/`boolean_bodies`（要多实体）、
`set_feature_expression`（要已命名表达式）。

## SW 三件事的结论（2026-11-05 11:00）

| 计划 | 结果 |
|---|---|
| ① 参数/前置状态 | `sw_measure_distance` **是我们给错点**（角点不在面上），改面中心点后 10.0 mm 通过；`sw_scan` 改成扫"没被 SW 打开"的副本目录后通过 |
| ② 上游 swkit 小 bug | `insert_component` 三层坑全修（8 参签名 + 晚绑定 + 自己找装配体文档）→ 0→1→2 组件真通；`cmd_scan` 的 getsize 加保护 |
| ③ 面草图 | hub 新增 `sw_create_sketch_on_face`（选面 → `SketchManager.InsertSketch`）→ `sw_sketch_convert_entities` **第一次真通过**（segments 0→4） |

**仍然卡住的（诚实记录）**：
* `get_dimension` / `set_dimension`：我们建出来的模型里**根本没有命名尺寸**（矩形草图不会生成 `D1@草图1`），要先用 `AddDimension2` 造一个尺寸才有得读——需要再加一个 hub 工具（`sw_add_sketch_dimension`）；
* `add_gtol`/`datum`/`weld`/`center_mark`：`drawing.symbol()` 要**先选中尺寸或视图**，还没做这层选择；
* `sketch_text`（`text_matches` 判据不过）、`sketch_circular_pattern`（backend error）、第二块面草图（InsertSketch 返回 False）仍未解决；
* `sw_close_document` 单跑能用，但在验收会话里会弹"是否保存"模态框把用例卡住 → 验收里不测；
* FEA（`sim_solve` 15 分钟）与 Motion 仍按"时间成本"排除。
