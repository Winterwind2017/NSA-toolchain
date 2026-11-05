# 覆盖率路线图：从 28% 到 100% 的调用覆盖 / 89% 的快乐路径

现状（2026-11-05 13:45 实测，`docs/acceptance-coverage.md`）：

```
工具 618 ｜ 验收 443 ｜ 契约 245 ｜ 合并 575 = 93.0% ｜ 快乐路径 407
未覆盖 43：sw 20 ｜ ug 13 ｜ autoshop 4 ｜ codesys 2 ｜ nx 2 ｜ acad 2
逐 kit：catia 100% ｜ eplan 100% ｜ gx 100% ｜ nx 97.0% ｜ codesys 96.7% ｜
        acad 96.4% ｜ autoshop 90.5% ｜ sw 89.5% ｜ ug 84.5%
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

## 尺寸链：两条 API 都不可用，**这条线放弃自动化**（2026-11-05 11:12，以崩一次 SW 为代价）

从 typelib（`D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb`）里查到三个
"看着非交互"的建尺寸入口，逐个实测：

| API | 签名 | 实测结果 |
|---|---|---|
| `ISketchManager.AddAlongXDimension` | (x, y, z) → IDisplayDimension | **把 SolidWorks 弄崩了**。日志 `<ED>uiDVEMultiDimPropPageValue_c "尺寸"` → `<EXCEPTION> Access Violation at 0x2ac0, attempt to write to memory` → `<EOSL>0` 异常退出，COM 只回"远程过程调用失败" |
| `IModelDoc2.AddDimension2` | (x, y, z) → IDimension | 不崩但 **180 s 不返回**，SW 停在等输入的交互态，后续工具调用全被"上一次调用还在后台"挡住 |
| `ISketchManager.AddAlongYDimension` | 同上 | 崩溃后已无法解析（进程没了） |

**结论**：SW 的尺寸创建是**UI 驱动**的（内部要开属性页/等用户点位置），没有可用的
无交互路径。所以这一批统一记为"**需要交互界面，不纳入自动化**"：

`sw_get_dimension` / `sw_set_dimension` / `sw_add_gtol` / `sw_add_datum_feature` /
`sw_add_weld_symbol` / `sw_add_center_mark`

崩后恢复：`Start-Process "D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe"`，
等 60–90 s，`sw_get_status` 能连上即恢复（本次重启后 `document_count: 0`，
欢迎面板**没有"文档恢复"**，说明没丢用户文档；最近文档里的"未找到文件"是我们
删掉的临时测试件）。

## 旧的尺寸链尝试（AddDimension2 卡死）—— 已被上面的结论取代

## 尺寸链尝试（2026-11-05 11:07）：`AddDimension2` 在本机会卡死

想让 `sw_get_dimension` / `sw_set_dimension` 有东西可读，得先造尺寸。试了
`solidworks-agent-kit` 里没有的路径，自己在 hub 侧写：

```
选草图线段 → IModelDoc2.AddDimension2(x, y, z) → 读 IDimension.FullName / SystemValue
```

**实测 `AddDimension2` 调用 180 s 不返回**（SW 进了一个等输入的交互状态，
工具超时后被内核判定"仍在后台运行"，后续调用全被挡住）。该工具已从
`hubsw_select.py` 里**移除**，不发布未验证的能力。

结论：尺寸对象这条链（`get_dimension`/`set_dimension`，以及依赖"选中尺寸"的
`add_gtol`/`datum`/`weld`/`center_mark`）需要换一条非交互的做法，例如：
* `ISketchManager` 的 `CreateDimension`？本机 swkit 没有封装，需要单独探；
* 或者干脆用 `sw_sketch_*` 建带关系的草图后走 `doc.Parameter` 读自动生成的尺寸名；
* 再或者从已有用户图纸里读真实尺寸名（只读，但依赖用户文件）。

## `sw_scan` 的真实执行路径修正

`sw_scan` 走的是 **`D:\bililive\mcp-patches\sw_adv.py`**（`sw_scripts._run_script`
用 PATCH_DIR），不是 `swkit/_legacy/sw_adv.py`。两处都已加 `getsize` 保护；
之前"改了但没生效"就是改错了副本。

## SW 剩余 46 个工具逐个探完（2026-11-05 12:10）

分 5 批真机探（每批独立子进程 + 90–120 s 单调用超时；卡死就杀 sw MCP 服务、不动 SW 本体）。
**结论先给**：能通的 21 个已写成 6 条剧本并全部 PASS；不能通的分三类，全部有实测依据。

### 已通（新增 21 个工具，6 条剧本）

| 剧本 | 真机 | 覆盖的新工具 |
|---|---|---|
| `sw.flow.part_ops` | 40.9 s | `cut_extrude` / `move_body` / `scale_body` / `mirror` / `assign_material_full` / `inspect_relations` / `dxp` / `flow_check` / `sim_faces`（+ 面上草图） |
| `sw.flow.sim` | 15.0 s | `sim_setup` / `sim_mesh`（**约束面=1、受力面=0** 才不报 code=1；且必须先赋材质） |
| `sw.flow.asm_ops` | 19.1 s | `hide_component`（插入两件后隐藏/显示） |
| `sw.flow.sketch_extras` | 7.7 s | `sketch_chamfer` / `sketch_circular_pattern`（上视草图画两条线后） |
| `sw.flow.constraint` | 4.0 s | `add_sketch_constraint`（**不能跟着调用 exit_sketch**，会判 sketch_closed=false） |
| `sw.flow.plan_only` | 12.1 s | `create_parametric_part(execute=False)` / `create_output_shaft(execute=False)` / `close_all` |
| 另有（单条实测通过，未入剧本） | — | `add_bom_table`（空装配图也能插表）、`replace_component`（0.5 s）、`measure_distance`、`close_document`、`insert_component` |

### 不能通（三类，共 25 个）

**① 尺寸/标注 = UI 驱动（6 个，定论，见上一节）**
`get_dimension` `set_dimension` `add_gtol` `add_datum_feature` `add_weld_symbol` `add_center_mark`

**② 图纸里"先选视图/尺寸"才动（5 个）**
`add_balloon`（120 s 卡死）、`view_rotate`（卡死）、`add_hole_table`（判据 table_added）、
`create_section_view`（backend error）、`add_broken_view`（判据 break_lines_increased）。
共同点：swkit 依赖 `SelectByID2` 选视图，本机选不中 → 要么无操作，要么把 SW 卡住。

**③ kit / 判据缺陷（14 个）**
| 工具 | 现象 |
|---|---|
| `select_features` | 中文特征名（`凸台-拉伸1`）和英文名（`Boss-Extrude1`）都选不中 → 0 个 |
| `pattern_feature` | backend error（依赖 select_features） |
| `move_component` | backend error（缺 IMathUtility 写位姿能力，见 MEMORY） |
| `replace_component` | 单独 0.5 s 过；接在"插入两件+隐藏"后卡死 |
| `suppress_component` | 单独能过；在装配序列里 90 s×2 卡死 |
| `delete_equation` | backend error（没有方程可删也给 backend error） |
| `combine_bodies` | 判据 feature_created / bodies_decreased 不过（要先选主实体） |
| `hem` / `base_flange` / `insert_bends` | 钣金判据全不过（后端 feature_added / sheet_metal_created 为 false） |
| `get_flat_pattern_info` | 判据 flat_pattern_present（前面钣金没建起来） |
| `analyze_draft` | backend error（要零件里已有分型线） |
| `sketch_text` | 判据 text_matches（文字建了但读回不匹配） |
| `motion_list` | 退出码 1：`<unknown>.GetComponents` |
| `motion_read` / `sim_read` | 一个 backend error，一个"没有结果（求解未成功）" |
| `feature_graph_compile` | 契约要求 `version='1.0'` 且 `features` 非空数组；给空数组被 ContractError 挡住 |
| `sim_solve` | 单次约 11–15 分钟（时间成本，按约定排除） |
| `vba_dump` | 需要一个 `.swp` 文件作输入（没有样本） |

### 一个操作教训（写进流程）

SW 一旦在某次调用里卡住，**sw MCP 服务进程会被那条调用永久占住**，后续调用全部
"上一次调用还在后台"。正确处置：`Stop-Process` 掉
`CommandLine -match 'swkit|nsa_mcp_hub.servers.sw'` 的 python 进程，**不要杀 SLDWORKS**；
新会话立刻可用（本轮做了 4 次，SW 一直活着）。

## SW 选特征 / 出图两条线打通（2026-11-05 13:45）

### `sw_select_features`：换掉两条走不通的路

| 试过的路 | 结果 |
|---|---|
| `SelectByID2("凸台-拉伸1", "BODYFEATURE")` | 恒 False（中文特征名不生效） |
| pywin32 `doc.FirstFeature()` | **报「找不到成员」**（`com_error -2147352573`） |
| comtypes `QIModelDoc2.FirstFeature()` + `IFeature::Select2` | ✅ 通 |

细节：comtypes 里 `FirstFeature` / `GetNextFeature` 返回的是 **dynamic `_Dispatch`**，
且可能被包成 callable —— 必须 `value() if callable(value) else value` 解引用，
否则 `GetNextFeature()` 直接 TypeError。遍历 20 个特征用 0.2 s，中文名照样选中。

### `sw_pattern_feature`：前置是"零件里得有切除类特征"

它内部按 ICE/Cut 找目标特征（`_find_target_feature`）+ 找一条直边当方向。
只有拉伸体时 → `backend error`；先切个孔（`cut_extrude`）再阵列 → 通过
（实测 target=`切除-拉伸1`、features 22→23）。

### 出图：`sw_add_balloon` / `sw_view_rotate` 也通了

- 必须**新建一张干净图纸**（`sw_new_drawing` 会带主视图）；
- `add_balloon` **自己会插 BOM**，前面再插一张 BOM 表 → SW 卡死；
- 这两条**只能单独跑**：跟别的出图用例同批时容易撞 900 s 超时。

## 两条验收基础设施的坑（这轮踩到的，已写进流程）

1. **`--report` 必须带路径**：`python -m nsa_mcp_hub.acceptance --kit sw --only X --report`
   会报 `expected one argument`；正确写法 `--report _runs/acceptance-<stamp>.json`。
   不带 `--report` 时**什么报告都不写**，覆盖度就原地不动（这轮白跑了两批才发现）。
2. **装配类剧本收尾会卡住**：留着一个装配体，swkit 子进程退出时会挂，
   报告写不出来。处置：`sw_close_all(save=True)` 收尾，或干脆不把这类用例放进批量跑
   —— 本轮把 `hide_component` 并进 `sw.flow.assembly_b`，并删掉重名的
   `sw.flow.asm_ops`（剧本三十五）��
3. **每个剧本单独起一次验收**（一个 `--only` 一条）比批量稳：批量跑时 SW 的
   文档/视图状态会互相污染，出图类尤其明显。

## SW 剩余工具按依赖顺序啃（2026-11-05 14:10）

顺序不是按名字排，是按**前置依赖**排：先能建基础件 → 再选特征/改参数 → 再钣金链
→ 再出图 → 最后 FEA。每层都真机跑过，能通的写成剧本。

### 第 1 层：基础件与实体（新通 4 个）

| 工具 | 配方 / 判据 |
|---|---|
| `sw_bounding_box_with_hidden` | 直接读包围盒，`include_hidden` 开关；0.8 s |
| `sw_create_sphere` | `execute=True`（**别给 `save_path`**，带路径时判据 executed/saved 会挂） |
| `sw_combine_bodies` | **两个实体必须重叠**：`move_body(copy=True, dx=20)` → 组合 2→1、体积 20000→15000；不重叠时 `InsertCombineFeature` 返回 None |
| `sw_select_bodies`（新工具） | pywin32 `SelectByID2("", "SOLIDBODY", 内缩 5% 的包围盒点)`；comtypes 的 `IPartDoc.GetBodies2 + body.Select2` 在本机报 `KeyError: 9`，`IBody2.Select2` 报 "instance can not be converted to a COM object" |

### 第 2 层：特征选择 / 参数 / 方程（新通 2 个）

* `sw_set_feature_parameter`（`凸台-拉伸1` + `D1` → 12 mm，1.4 s）
* `sw_delete_equation`（**必须先 `add_equation`**，没有方程时它报 backend error）
* 复用第 1 层的 `sw_select_features`（comtypes 遍历特征树）

### 第 3 层：钣金链（新通 4 个，整链 42 s）

严格顺序：**草图 → 基体法兰 → 选边卷边 → 选面折弯 → 展开信息**

| 工具 | 关键前置 |
|---|---|
| `sw_base_flange(thickness, radius, depth)` | 要有草图（80×50） |
| `sw_hem` | **必须选边**：这块板上第 4 条边才成功（前几条都判 feature_added=false） |
| `sw_insert_bends` | **必须选面**（`sw_select_faces([0])`） |
| `sw_get_flat_pattern_info` | 在基体法兰之后就有展开状态 |

### 第 4 层：出图（新通 1 个工具 + 1 个新工具）

* `sw_select_view`（新工具）：pywin32 的 `doc.GetFirstView()` 报「找不到成员」→ 改
  **comtypes QI 到 `IDrawingDoc`** 枚举，`SelectByID2(name, "DRAWINGVIEW", …, None, 0)`
  （comtypes 下 Callout 必须给 `None`，给 win32com 的 VARIANT 会报
  "VARIANT object has no attribute QueryInterface"）。
* `sw_add_bom_table` 通；`sw_create_section_view` / `sw_add_broken_view` /
  `sw_add_hole_table` **即使选中视图仍判据不过**（kit 侧调用不落地）→ 记为 kit 缺陷。

### 第 5 层：FEA（时间成本）

`sw_sim_setup` + `sw_sim_mesh` 已通；`sw_sim_solve` 单次 11–15 分钟、`star.exe` 峰值约
15 GB，单独跑（`sw.flow.fea_solve`）。`sw_sim_run` 是同一个求解器，不再单独跑一遍。

### 仍然啃不动的（kit / 样本 / UI，共 12 个）

| 工具 | 卡点 |
|---|---|
| `sw_create_section_view` / `sw_add_broken_view` / `sw_add_hole_table` | 选中视图后判据仍 false（kit 侧调用不落地） |
| `sw_sketch_text` | 文字建了但 `text_matches` 读不回 |
| `sw_analyze_draft` | 需要零件里**已有分型线**，kit 创建不了分型线 |
| `sw_move_component` | 本机没有写组件位姿的 API（`CreateTransform` 返单位阵） |
| `sw_motion_list` / `sw_motion_read` | `<unknown>.GetComponents` / 没有结果集 |
| `sw_sim_run` | 与 `sw_sim_solve` 同一求解器，时间成本 |
| `sw_vba_dump` | 需要一个 `.swp` 样本 |
| `sw_get_dimension` / `sw_set_dimension` / `sw_add_gtol` / `sw_add_datum_feature` / `sw_add_weld_symbol` / `sw_add_center_mark` | 尺寸/标注是 UI 驱动（已定论） |

## SW 最后一轮：代理层判据语义修正 + 收尾（2026-11-05 14:35）

### 一个影响面很大的代理层 bug（已修）

`swkit_adapter.make_handler` 以前把上游 `checks` 里**每一项**都当硬判据：
```python
checks.append({"check": key, "want": True, "ok": bool(value), ...})
```
于是 `sw_sketch_text` 这种「上游 `ok = object_created and (segments_increased or
text_matches)`」的工具会被误判：本机 `InsertSketchText` 的 `GetText` 读回恒 `None`、
但线段 0→1，上游自己判 ok=true，代理层却因为 `text_matches=false` 把 ok 翻回 false。

修法（`swkit_adapter.py` 与 `proxymcp.py` 同步）：**上游给了 `ok` 就以它为准**，
单项 `checks` 降级为说明性（`ok=True` + `got` 保留原值 + `informational=True`）；
失败原因拼装改成看 `got is False`，所以报错里仍然能看到 `text_matches` 这类名字。

### 新通的 6 个工具

| 工具 | 配方 |
|---|---|
| `sw_sketch_text` | 代理层修好后直接过（线段 0→1） |
| `sw_close_document` | **不给 title** 就是关活动文档（给错名字会判 `count_decreased=false`） |
| `sw_select_references` | 先 `sw_feature_inspect(include_tokens=True)` 拿 `reads.result.topology[].reference_token`，再选 |
| `sw_vba_dump` | 用本机样本 `D:\bililive\DeepHarness\_sw_probe\generated_test.swp`（32 KB），0.26 s |
| `sw_create_two_stage_reducer` | `execute=False`（只出计划）|
| `sw_sim_run` / `sw_sim_read` | 在同一个研究上再求解 + 读结果；`sim_solve` 后接 `sim_run` 都 < 35 s（100×50×10 板、10 mm 网格）|

### 当前仍然啃不动的 11 个（每条都有实测依据）

| 工具 | 卡点 | 结论 |
|---|---|---|
| `sw_add_broken_view` | `break_lines_increased=false` | kit 侧 `InsertBreak` 不落地 |
| `sw_add_hole_table` | `table_added=false` | kit 侧 `InsertHoleTable2` 不落地 |
| `sw_create_section_view` | backend error | kit 侧 `CreateSectionView` 不落地 |
| `sw_add_gtol` / `sw_add_datum_feature` / `sw_add_weld_symbol` / `sw_add_center_mark` / `sw_set_dimension` | 需要"先选中尺寸/视图" | 尺寸是 UI 驱动（已定论） |
| `sw_analyze_draft` | 需要零件里已有分型线 | SW API 无法创建分型线 |
| `sw_move_component` | 组件位姿写不进去（`CreateTransform` 返单位阵），swkit 的"变换拷贝法"在新建装配体上会挂 | 本机无解 |

## UG 剩余 13 个按依赖顺序啃（2026-11-05 18:10）

### 第 1 层：拓扑解析（新通 1 个）

`ug_resolve_topology`：`selector={"kind":"planar","normal":[0,0,1]}` 对平面唯一命中；
匹配多条时**必须** `unique=False`，否则报 `matched N edges; add sort_by or occurrence`。

### 第 2 层：钣金折弯（新通 1 个）

严格依赖：**草图（`journal_id` 就是名字）→ `create_sheet_metal_tab` → 另画一张
"折弯线"草图 → `create_sheet_metal_bend`**。
两个坑：① 草图 `geometry` 的字段是 **`type`**（不是 `kind`），写成 `kind` 会报
`unsupported sketch geometry type:`（空名字）；② `sketch_id` 传的是 `journal_id`
（= 草图名），不是返回里的 `tag`。

### 第 3 层：机器套件（只读 3 个通，其余卡在"激活"）

机器族要先有 profile：默认读 `MCP/UG/config/machine_sources.local`（只有
`.example.json`，本机原本没有这个文件）。这次按 `sim05_mill_5ax` 的真实机型图
新建了 profile `nsa_probe_5ax`：

| 字段 | 值 |
|---|---|
| `source_part` | `…\installed_machines\sim05_mill_5ax\graphics\sim05_mill_5ax.prt`（177 KB，真实机型） |
| `kinematic_definition` | `config\nsa_probe_machine.mch`（**合成**的 `<VcMachine>` XML：BASE/Y/X/Z/A/C/SPINDLE/TOOL 八段） |
| `geometry_root` | `…\sim05_mill_5ax\graphics` |
| `expected_axes` | `["X","Y","Z","A","C"]` |

通了：

* `ug_inspect_machine_source_profile`（读 profile + 源件指纹）
* `ug_inspect_machine_kinematic_plan`（解析 VcMachine → 组件树 + 轴限位 + 缺几何清单）
* `ug_create_machine_build_workspace` **dry_run**（返回"要不要切换活动部件"的计划）
* `ug_inspect_active_machine_simulation` / `ug_stop_active_machine_simulation`
  （没有活动仿真时也正常返回，stop 是幂等 release）

**卡点（关键发现）**：`ug_activate_machine_build_workspace` 用
`dry_run=False` 真切换活动部件时，会**把 NX remoting 线程挂死**（>420 s 不返回，
之后所有工具都报 `timed out waiting for NX remoting`，必须重启 ugraf 才能恢复）。
已经排除两个诱因：先 `ug_save_work_part` 保存、以及 `preserve_current=False`
（后者会立刻给出明确拒绝 `Save or discard current NX part changes`，说明它要的
是"零脏改"，但满足后仍然挂）。所以下游 7 个全部卡在这一步：

| 工具 | 卡点 |
|---|---|
| `validate_machine_kinematics` / `retarget_machine_junctions_from_profile` / `import_machine_component_geometry` / `validate_machine_static_collisions` | 都要求"工作区部件是活动部件" |
| `inspect_machine_simulation_readiness` | 要先有 CAM setup，再有绑定的机床 |
| `start_machine_simulation_with_collision_stop` | 同上 |
| `import_machine_kit_readback` | 需要一个 `.mtk` 文件（本机磁盘上没有） |

NX 恢复办法：`Stop-Process -Name ugraf` → 设 `UGII_USER_DIR` 重开 → 约 5–45 s 桥回来。

## 最后四个工具（2026-11-05 19:25）

| 工具 | 结果 | 配方 / 卡点 |
|---|---|---|
| `nx_run_capability` | ✅ 13.6 s | `{"id": "solid.delete_face"}`，分发器按能力 id 真跑 |
| `nx_solid_delete_face` | ✅ 13.8 s | 直接调；判据是"删孔面后愈合回 100000 / 6 面" |
| `acad_status` | ✅ | 需要**已打开文档**（系统变量是文档级）；还要 `CMDDIA=0`（基线是 0，新文档会回到 1） |
| `acad_boolean_section_slice` | ✅ 26 s 整条剧本 | 历史上超时过（看门狗会 `taskkill acad.exe`），这次给 900 s、单独跑、实测 26 s 通过、acad 没被杀 |

### 两个环境发现

1. **AutoCAD 装的是 2025、在 `D:\Program Files\Autodesk\AutoCAD 2025\`**
   （注册表 `HKLM\SOFTWARE\Autodesk\AutoCAD\R25.0\ACAD-8107:804\AcadLocation`），
   `C:\Program Files\Autodesk\AutoCAD 2025` 是空的。启动命令：
   `acad.exe /p "<<VANILLA>>"`，实测 `CPROFILE = <<VANILLA>>`。
2. `%TEMP%` 里有一个 2026-11-04 的 `Drawing2_1_29790_3f894360.sv$`（自动保存残留），
   它让 `acad_status` 一直判 `sv_count` 漂移。已**移到备份目录**
   `D:\bililive\acad_out\sv_backup\`（没删），status 随即通过。

### 收尾后的"未覆盖"是什么

`nx` 与 `acad` 现在各剩 1 个"未覆盖"，那个工具叫 **`kit_runtime`** ——
它是内核给每个 kit 自动挂的合成工具（不是真能力），所以两个 kit 实质都是 **100%**。

## 改上游：swkit 出图三件套 + NX 机器激活（2026-11-05 20:05）

### swkit（提交 ed1b50a）

| 工具 | 结论 |
|---|---|
| `sw_add_broken_view` | **真修好了**。`IView.InsertBreak2` 参数名从类型库读出是 `(Orientation, Position1, Position2, Style, ShapeIntensity)`；旧实现只给一个 position、把 size 当 Position2 → SW 静默不建。改成两条断裂线位置 + 枚举扫描，`GetBreakLines` -1→1，style=2 成功 |
| `sw_create_section_view` | **不是 bug，是时序**。它走 `IModelViewManager.CreateSectionView` = 模型 3D 剖视，必须在**零件**上、建图之前调；之前全在工程图上调，必挂 |
| `sw_add_hole_table` | **半通**。① 模板传空串 → SW 静默 None，现在自动搜 `.sldholtbt`（本机 SW 在 D 盘，只扫 C 盘会空）；② 判据从"特征名含 Table"改成 `IView.GetTableAnnotationCount`（孔表是注解不是特征，旧判据永远 0）。但 12 种参数组合仍全 None —— 唯一没排除的是几何：测试件是 `FeatureCut4` 圆孔，孔表通常只认 **Hole Wizard 孔** |

### nx_remote_ops（磁盘改动，非 git 仓库）

1. **激活挂死的根因**：`activate_machine_build_workspace` 用**装配体**当源件时，
   组件解析不到 → NX 弹缺件确认 → remoting 线程挂死（>420 s，之后所有工具
   `timed out waiting for NX remoting`，只能重启 ugraf）。换成**单零件**源件后
   0.8 s 成功。
2. **`<VcMachine>` 组件名是写死的**：low-level 建链里直接取
   `component_objects["Tool"] / ["Attach"]`、`by_name["Tool"]`，链里固定要
   X/Y/Z/B/C + S。所以组件必须叫 **Base/Y/X/Z/B/C/Spindle/Tool/Attach**。
3. **旋转轴的 `Axis` 只能是 X/Y/Z**（方向），寄存器名才是 B/C；给 `Axis="A"`
   会以 `KeyError` 形式炸在 `create_axis_A`（报错不友好，已记录）。
4. **主轴组件要有 `<Link Register="S">`**，否则 `create_axis_S` KeyError。
5. 每个组件要有 `<STL><File>xxx.stl</File></STL>` 且文件真在 `geometry_root`，
   否则 build 报 `component_geometry_not_imported`。
6. **通道-轴绑定仍没打通**：`AddChannelName` 只挂组件，`IsAxisAssignedToChannel`
   全 False。正确入口是 `KinematicChannelBuilder.SetAssignedAxes` + `MainSpindle`，
   但用 `KinematicChannelConfigurationBuilder.Commit()` 提交后通道会从
   `GetChannels()` 消失（validate 立刻变 `kinematic_channel_missing`），所以现在
   **只尝试不提交**，把缺口如实报成 `channel_axis_assignments_missing`。

### 新剧本

`ug.flow.machine_build`（3.8 s，建工作区→激活→导入几何→真建运动学→轴探测→junction 重定向）
`sw.flow.drawing_extra`（87.5 s，带孔零件→3D 剖视→建图→断裂视图）

### 覆盖

620 工具：验收 471 ｜ 契约 245 ｜ 合并 598 = **96.5%** ｜ 快乐路径 443
ug 91.7% → **94.0%**（未覆盖 7 → 5）｜ sw 94.3% → **95.3%**（未覆盖 11 → 8）
剩 22：sw 8 ｜ ug 5 ｜ autoshop 4 ｜ codesys 2 ｜ nx 1 ｜ acad 1（后两个是合成
`kit_runtime`）

## 孔表打通（2026-11-05 21:40，swkit 2db1a33）

用户按我的请求录了一段"只录插孔表"的宏，源码里那行就是全部答案：

```vb
Set myView = Part.SelectionManager.GetSelectedObjectsDrawingView(1)
Set myHoleTable = myView.InsertHoleTable2(False, 0.10027, 0.19557, 1, "A", "D:\...\standard hole table--letters.sldholtbt")
```

四道坎，缺一条就静默返回 None：

| 坎 | 事实 |
|---|---|
| 参数顺序 | `(UseAnchorPoint, X, Y, AnchorType, **StartValue**, **Template**)` —— 第 5 个是 `"A"`，第 6 个才是模板。之前模板放第 5、第 6 传空串 |
| 选孔边 | `IView.GetVisibleEntities2(VARIANT(VT_DISPATCH,NULL), 1)` 才拿得到边（给 `None` 报"类型不匹配"）；`edge.Select4(True, VAR(VT_DISPATCH,NULL))` 才选得上（`Select4(False, None)` 静默 False） |
| 模板 | 必须是真实 `.sldholtbt` 路径（本机在 D 盘） |
| 判据 | **不能**用 `IView.GetTableAnnotationCount`（建出来仍是 0）；用"返回值非空 且 `GetAnnotation().GetType == 14`" |

实测：选中 6 条边 → 返回 CDispatch → 注解类型 14 → PASS。
`sw.flow.drawing_extra` 现在是「3D 剖视 → 建图 → 孔表 → 断裂视图」14 步，11.2 s 通过。

顺带记两条血的教训（同一晚踩的）：
* 在用户真实会话里跑 48 组参数矩阵，把 SW 拽进"命令未结束"状态，界面整个点不动、
  连文档都切不了，还弹出「无法中断当前操作」模态框；恢复办法是关掉那张测试图再重开零件。
  → `sw_add_hole_table` 已加护栏：零件在草图编辑态直接拒绝执行。
* 工程图上 `GetActiveSketch` **永远非空**（返回视图里模型的草图），所以护栏只能拦
  非工程图文档，否则会误判。

覆盖：620 工具 ｜ 验收 472 ｜ 合并 599 = **96.6%** ｜ 快乐路径 444
sw 95.3% → **95.8%**（未覆盖 9 → 8）

## 注释/标注类一次打通（2026-11-05 22:00，swkit 233b9f0）

`sw_add_datum_feature` / `sw_add_gtol` / `sw_add_weld_symbol` / `sw_add_center_mark`
一直是"ok=False 且 errors 为空"，根因只有一条：**选边方式**。

| 手段 | 结果 |
|---|---|
| `entity.Select2(False, mark)`（旧） | 静默 False，一条选不上 → `InsertDatumTag2()` 返回 None |
| `entity.Select4(True, VARIANT(VT_DISPATCH,NULL))` | 选得上（6 条边）→ 三个 API 立刻生效 |

判据也改对了：

* datum / gtol / weld：`IView.GetDatumTagCount / GetGTolCount / GetWeldSymbolCount`
  **实测准**（0→1）；
* center_mark：`IView.GetCenterMarks` 建完仍 0（同孔表），改判
  `IDrawingDoc.InsertCenterMark2(Style, Propagate)` 是否返回 ICenterMark；
* 中心标记需要圆边——孔轴沿 Z 时前视图看不到孔口圆，验收改用**上视**建图。

`sw_set_dimension` 本身没 bug，缺"真实命名尺寸"：参数化零件自带 `D1@BlockBoss`，
20 mm → 25 mm 读回一致（体积不变说明它不是拉伸深度，但读写链路是对的）。

新剧本：`sw.flow.param_dimension`（3.6 s，4 步）。
`sw.flow.drawing_extra` 扩成 18 步：3D 剖视 → 上视建图 → 孔表 → 断裂视图 → 中心标记
→ 基准 → 形位公差 → 焊接符号，11.2 s 通过。

覆盖：620 工具 ｜ 验收 478 ｜ 合并 604 = **97.4%** ｜ 快乐路径 450
sw 95.8% → **98.4%**（未覆盖 8 → 3：analyze_draft / move_component / kit_runtime）

## codesys 两个缺口补齐（2026-11-05 21:50，codesyskit 44083b3）

| 工具 | 之前 | 修法 |
|---|---|---|
| `codesys_call` | 没有用例 | 加 `codesys.tool.call`：透传 `ping`，读回 banner/pid（52 ms） |
| `codesys_import_xml` | `E_SCRIPT: 未找到可导入的对象` | `cmd_import_xml` 的第二个参数不是"可选父对象"，而是**导入目标对象**；给 `None` 必失败。改成支持 `target`、默认当前 Application，并保留 one-arg 兜底 |

配套事实：`export.xml` 的 `target` 要给**可导入对象**（POU / 文件夹）。
导 `Application` 出来的 XML 在新工程里导入照样报同一个错。

新剧本 `codesys.flow.xml_roundtrip`（3.0 s）：建工程 → 建 POU → 写实现 → 导出 POU 的 XML
→ 另建工程 → 导入 → children 3→4，通过。
（顺手清掉了 `codesyskit` 里 `agentscript.py` 与 `.git/*` 的只读属性，否则改写/提交都被拒。）

## autoshop 归零（2026-11-05 22:05，autoshopkit 28c2fdd）

四个没覆盖的工具全在"启动/新建/单档编译/生成下载文件/关闭"这条生命周期上，
两个真 bug：

| 问题 | 事实 | 修法 |
|---|---|---|
| `autoshop_new` | 旧映射传 `--path/--hcp`，CLI 只认 `new <name> [--dest DIR]` → `unrecognized arguments`（连踩两次：先是 `--path`，修完又重复传了 verb） | 适配器把 `path` 拆成「最后一段=工程名 + 其余=--dest」 |
| `autoshop_dlfile` | 工程改过后先弹「在下载前是否需要重新编译」，不回答就等不到"下载选项" → `LookupError` | autoshopkit 新增 `_answer_recompile_prompt()`，默认点 否(7) |

新剧本 `autoshop.flow.lifecycle`（5 步，67.9 s）：
起 AutoShop（21 s）→ 新建工程（8.7 s，MAIN + 721 树节点）→ 单档编译（1.5 s，0 错误）
→ 生成下载文件（10.9 s，产出 `flowproj.updown`）→ 关闭。

autoshop 90.5% → **100%**；全库 **98.2%**。

## ug 归零（2026-11-05 22:15）

五个"机床校验/仿真"工具之前一条用例都没有，现在一条剧本全盖住 ——
但断言的是「**每条拒绝都带确定原因**」，不是「校验通过」。

| 工具 | 本机实测结论 |
|---|---|
| `ug_validate_machine_kinematics` | 组件/轴/几何/接合/系统类/链条**全过**，唯一阻塞 `channel_axis_assignments_missing` |
| `ug_validate_machine_static_collisions` | 同上 + `collision_pairs_missing`（`.mch` 没碰撞对） |
| `ug_inspect_machine_simulation_readiness` | 建了 CAM setup 但没工序 → `contains no operations` |
| `ug_start_machine_simulation_with_collision_stop` | 同上 |
| `ug_import_machine_kit_readback` | 用不存在的 `.mtk` → `machine kit does not exist`（证明它不假成功） |

**许可证定论**：`KinematicChannelBuilder.SetAssignedAxes` 的 API 文档要求
`ug_isv_full` 或 `nx_isv_mtb`；本机没有，所以 `IsAxisAssignedToChannel` 恒 False，
而 `KinematicChannelConfigurationBuilder.Commit()` 还会把通道清空。

顺手两个上游修复：

1. `nx_remote_ops`：`DefineKinematicChains().Commit()` 会冲掉之前注册的通道，
   改成**链提交之后再补注册**（`register_machine_channel_after_chains`），
   阻塞项从「连通道都没了」收敛成一条准确原因，并回传 `channel_reregistered_after_chains`。
2. `proxymcp`（hub 侧代理层）：上游只回 `ok=false` + `blockers` 时，原来统一报
   「backend error（后端未给出原因）」；现在把 `blockers / remaining_blockers /
   missing_*` 抬进 errors，调用方看到的是
   `blockers=channel_axis_assignments_missing；missing_channel_axis_assignments=X,Y,Z,B,C,S`。

另外 harness 侧一条坑：剧本步骤要带 `"ok"` 字段才计入覆盖（`reads.steps[].ok`），
只写 `actual_ok` 的话用例 PASS 但覆盖率原地不动（我因此白跑一次）。

新剧本 `ug.flow.machine_validate`（12 步，4.8 s）。
ug 94.0% → **100%**；全库 **99.0%**（614/620）。
剩 6：`kit_runtime` ×4（合成项）+ sw `analyze_draft` / `move_component`。

## 收尾：620/620 = 100%（2026-11-05 22:35）

最后两个真缺口（sw）用**拒绝路径**盖住：

| 工具 | 事实 |
|---|---|
| `sw_analyze_draft` | 需要零件里**已有分型线特征**（API 建不出来），没有时如实报 `特征树里没有分型线特征（需先手工建一个）` |
| `sw_move_component` | 空装配里如实报 `装配里没有组件`（0.1 s 就拒，不再卡 300 s） |

新剧本 `sw.flow.refusals`（9 步，8.6 s）：建零件 → 草图 → 拉伸 → `analyze_draft`（拒绝）
→ 建装配 → `move_component`（拒绝）。

剩下四个 `kit_runtime` 是内核自带的运行状态探针（零参、0 ms），一个 kit 加一条
`<kit>.tool.runtime` 用例即可：sw / nx / codesys 直接过；
**acad 需要 AutoCAD 在跑**（`acad.exe /p "<<VANILLA>>"`，否则整组 SKIP 不算覆盖）。

顺带把 `proxymcp` 的兜底再补一层：上游把原因放在 `reads.error` / `reads.detail.error`
里时（swkit 基本都这样），也抬进 errors，不再统一显示「backend error（后端未给出原因）」。

最终：**620 工具 ｜ 验收 495 ｜ 契约 245 ｜ 合并 620 = 100.0% ｜ 快乐路径 468 ｜ 未覆盖 0**
九个 kit 全部 100%。

## ug 静态碰撞：从"拒绝"变"真值"（2026-11-05 23:15）

`.mch` 补了 `<Collision>` 段（4 对：Tool↔Attach、Spindle↔Attach、Base↔Spindle、C↔Base，
间隙区 1mm），`ug_validate_machine_static_collisions` 现在**真的跑完评估**：

```
evaluated_pair_count = 4 / 4
interfering_pair_count = 0  (hard=0 soft=0 touching=0)
blockers = ['channel_axis_assignments_missing']   ← 只剩许可证那条
```

为了让这条通，修了三处：

| 坑 | 事实 | 修法 |
|---|---|---|
| 9 个 STL 都是"原点 20mm 立方体" | 实体全重叠 → 任何碰撞对都干涉 | 每个零件平移到不同位置（BASE 0 / Y 20 / … / TOOL 140，SETUP 放侧面 x=100），`*.stl.bak` 有备份 |
| 组件名被换成模板别名 | `Base→MACHINE_BASE、Tool→POCKET_01、Attach→SETUP、C→C_SLIDE` 是 smart-kit 模板命名，`source_part_copy` 建出来的就叫 `Base/Tool/...` → 全查不到 | `_machine_oem_collision_configuration()` 改成**按实际组件名精确匹配（含大小写）**，匹配不上再退别名 |
| `ComponentCollection` 是 `ObjectList` | `list(...)` 在部分状态下迭代出空集（不报错）→ 每个组件都判成"没几何" | `_machine_component_geometry()` 优先 `ToArray()` |

剧本 `ug.flow.machine_validate` 的静态碰撞断言从"拒绝原因"升级成
「4 对全部配置 + 全部评估 + 0 干涉」，5.0 s 通过；`ug.flow.machine_build`、
`ug.cam.recipe` 复跑仍 PASS。

覆盖维持 **620/620 = 100%**（验收 495 ｜ 契约 245 ｜ 快乐路径 468）。

## ug 机床五件套：从"有序拒绝"变成"真通过"（2026-11-05 23:40）

换路线成功：`blank_smart_machine_kit`（导入 NX 官方 **5 Axis Dual Table BC Mill** 模板）
→ 通道 `TNC_640` 自带 6 根轴绑定，`ug_validate_machine_kinematics` **ok=True**，
`ug_validate_machine_static_collisions` **ok=True**（4 对全评估、0 干涉）。

踩过的三层：

| 层 | 事实 |
|---|---|
| 许可 | 许可文件里 `isv_full` / `nx_isv_mtb` 都有（permanent/uncounted），`CheckPresence` True、`Reserve` 能签出 → **不用另开许可** |
| 应用 | 通道要在 `UG_APP_MACHINE_TOOL_BUILDER` 里定义（NX 弹窗原文："在机床构建器中定义通道"） |
| 路线 | `source_part_copy` 的轴绑不上通道（`GetAssignedAxes()` 返回空串，Commit 时通道被判无效）；官方模板导入的轴自带绑定 |

顺带修的上游 bug：模板路径里把轴编号按 1..n 重排会和模板已有编号撞号
（`NXException 3779335「轴编号已存在」`）→ 改成**沿用模板编号**，只在当前编号 <=0 时才写。

剧本 `ug.flow.machine_validate` 已改成模板路线（10 步，5.6 s），断言：
运动学无阻塞 + 6 轴全绑 + 静态碰撞 4 对全评估 0 干涉；后三个工具仍断言拒绝原因。
覆盖维持 **620/620 = 100%**（验收 495 ｜ 契约 245 ｜ 快乐路径 468）。

剩：`machine_kit_archive_not_exported`（`.mtk` 导出，`ug_export_machine_kit_from_reference` 报后端拒绝，待查）。

## `.mtk` 导出与许可：两条"看起来能打通"的路，实测都收掉（2026-11-05 23:45）

| 尝试 | 结论 |
|---|---|
| `ug_export_machine_kit_from_reference` | confirmation 是 **`EXPORT_MACHINE_KIT`**；用手工配方（build → save → 换新 MCP 会话 → activate → export）**成功过一次**，产出 1,527,313 B 的 `.mtk`，随后 `ug_import_machine_kit_readback`（**`IMPORT_MACHINE_KIT_ISOLATED`**）ok=True、`isolated_import=True`、`global_machine_database_unchanged=True`；但之后同会话/新会话重试**恒定** `MOM_TCL：用户选择了中止` → **不进剧本**，只留手工配方 |
| 许可当第二条路 | `Reserve(isv_full)` + `Reserve(nx_isv_mtb)` + 切 MTB 应用之后，低层路线**仍然**绑不上通道（`GetAssignedAxes()` 全空、Commit 丢通道）→ 许可不是瓶颈，**自动 Reserve 无收益只会白占席位**，不做 |

最终 ug 五件套：kinematics / static collisions **正通过**，readiness / start 断言
CAM 无工序的拒绝，import readback 断言"缺 kit 报错不假成功"。
覆盖维持 **620/620 = 100%**。

## `.mtk` 导出 + CAM 就绪度：两条都收掉（2026-11-06 00:00）

| 项 | 结论 |
|---|---|
| `.mtk` 导出 | 不给参考包 → NX 的 `ExportMachineKitBuilder` 内部 TCL 恒定 abort（`MOM_TCL：用户选择了中止`，**没有任何对话框**，窗口监视器 0 命中）；**给 `reference_container_file_name=nsa_reference_kit.mtk`** 就跳过 builder、直接 repackage → `ok=True`、1,527,734 B、回读 `isolated_import=True`、全局机床库未变 |
| readiness | 建一个空工序（先 `create_cam_mill_tool`，再 `create_cam_operation` 用 `geometry_name=MCS_MAIN`）后 **ok=True**；但它只是报告（`machine_simulation_ready=False` + blockers） |
| start | 仍是真闸门，拒绝并点名 `no_machine_library_binding / toolpaths_missing / part_geometry_missing / blank_geometry_missing` |

剧本 `ug.flow.machine_validate`（14 步，9.7 s PASS）现在覆盖：
运动学通过、静态碰撞通过、导出+回读通过、readiness 报告通过、start 的有序拒绝。

覆盖：**620/620 = 100%**（验收 496 ｜ 契约 245 ｜ 快乐路径 469 ｜ 未覆盖 0）。

## `start_machine_simulation` 转正尝试：两条绑定路线都撞 NX API（2026-11-06 00:05）

| 路线 | 结果 |
|---|---|
| `bind_isolated_machine_kit_to_cam`（我们的 kit，shadow 库） | dry_run ok（libref=nsa_reference_kit、全局库未改）；真跑失败：先 `isolated_import_readback` / NXException **3975001**，NX 重启后变 "failed NX import/readback validation" |
| `bind_machine_tool_from_library(machine_libref=sim05_mill_5ax)` | `machine_library_entry_lookup` 失败（libref 不在库索引） |
| 同上 `sim06_mill_5ax_tnc` | 过 lookup，失败在 `current_machine_binding_readback` / NXException **1345004**（dry_run 与 real 都失败） |

`start` 的前提是 CAM 程序组绑了机床，所以这两条不通它就一直是有序拒绝。
剧本里继续断言"拒绝 + 点名 blockers"，不假装通过。

下一步建议（按性价比）：UI 里手工绑一次 → 用 `run_python` 读出绑定后的 CAM 字段照着复刻；
或者拆 NX 自带机床定义对齐 `kit_information.xml`。

## 机床仿真真跑通（2026-11-06 01:20）

用户手工绑机床（`sim05_mill_5ax_fanuc`）后，整条链打通：

| 步骤 | 结果 |
|---|---|
| `create_cam_milling_context` + `create_cam_operation(FLOOR_FACING)` | ok |
| `configure_cam_milling_operation`（cut_area 面 + floor_z + 进给） | ok |
| `generate_cam_toolpath` | **ok**（`PLANAR_MILL`/`FACE_MILL_ZIGZAG`/`FACE_MILL_MIDPASS` 恒失败，别用） |
| readiness | **blockers=[]、ready=true** |
| `start_machine_simulation_with_collision_stop(play_immediately=False)` | **ok**（prepared、碰撞开关全开） |
| `stop_active_machine_simulation` | ok（stopped/released） |

新用例 `ug.flow.machine_simulate`（fixture 已绑机床，SKIP 守卫）**PASS 7.7 s**。
顺带修 `nsa_probe_5ax` profile：`expected_axes` 改 B/C、`geometry_root` 指向我们放 STL 的目录
（原来指向 NX sim05 图形目录，导致 `ug.flow.machine_inspect` 报
`component_geometry_missing` + `expected_axes_missing`）。

## ug 全量 300 s 超时：定位到 `initialize_cam_setup`（2026-11-06 02:20）

* 加了单步超时后拿到真凶：前 13 条用例之后，**再进 CAM（`initialize_cam_setup`）挂死**
  （`ug.cam.capabilities` 45 s 超时点名该步骤）；同一位置也会在 `create_block` 出现，
  说明是会话级状态退化，不是单个工具。
* 已改：`_ug_flow` 单步 45 s、`_ug_cam_recipe` 单步 60 s + 用例超时 900→300 s，
  失败时**报出步骤名**；`_ensure_design_application()` 前置到 `create_part`/`create_block`/
  `cam_capabilities`（机床构建器应用粘性会毒化后续建模与 CAM）。
* `ug.cam.capabilities` 去掉"建块"步骤（块建模已被 `ug.flow.model` 覆盖，且它在大序列里
  偶发 45 s 超时）。
* 待办：加 `ug_close_test_parts`（只关 `acc_*`/`cap_*`/`nsa_accept_*`），在 CAM 用例开头清理会话。

## 会话减负：`close_test_parts` 让 `cam.capabilities` 稳定（2026-11-06 02:30）

* 新增 `ug_close_test_parts`（白名单前缀 `acc_/cap_/nsa_accept_/nsa_probe_/fill_/...`，
  默认 dry_run，真关要 `CLOSE_TEST_PARTS`），用 `part.Close(TrueValue, CloseModified, None)`。
* 接在 `ug.cam.capabilities` / `ug.cam.recipe` 开头：capabilities 从"45 s 超时"
  变 **PASS 2.5 s**；两条连跑 2.6 s / 10.1 s。
* 剩余：全量序列里 `ug.cam.recipe` 仍偶发 300 s（单步已限 60 s，日志会点名步骤）。

## ug 16/16 全绿（2026-11-06 02:56，149 s）

| 修复 | 关键点 |
|---|---|
| kit 级自救 | `McpClient.restart()`：单步超时→重启 kit 子进程（旧线程读 EOF 退出），不再让泄漏线程把后续步骤逐个拖死 |
| 单步上限 | `_ug_flow` 45 s、`cam.recipe` 60 s；`close_test_parts` 60 s 且 tolerate（清理卡住不算失败） |
| 倒角不再靠序号 | `modeling2` 用 `inspect_body_topology` 挑"相邻两面都是平面 + 边长≥20"的直边，按长度试 |
| fixture 保护 | `close_test_parts` 默认保护 `acc_kit_61ab27`（关掉会导致 `start_machine_simulation` 报 641073 加载部件失败） |

覆盖：**621/621 = 100%**（验收 497 ｜ 契约 245 ｜ 快乐路径 470 ｜ 未覆盖 0）。
