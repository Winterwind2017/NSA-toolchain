# 收官说明（`v1.0-acceptance`）

> 这份文档回答三个问题：**这套东西现在是什么状态**、**怎么把它跑起来**、**哪些能力明确不可用**。
> 日期：2026-11-09 ｜ 代码版本：`nsa_mcp_hub.__version__ = 0.2.0` ｜ 里程碑 tag：`v1.0-acceptance`
> 数字口径全部来自实测（`docs/acceptance-coverage.md`、各 kit 的 `docs/UNSUPPORTED.md`），不引用旧结论。

---

## 1. 它是什么

一个 MCP 端点（stdio JSON-RPC 2.0），把 **9 个 CAD / PLC 自动化内核**收进同一套返回结构与验收口径。
每个 kit 仍是独立进程（COM 单实例、NX 冷启动、GX 抢焦点这些特性各自关在自己进程里）。

```
MCP 客户端（DSH 等）
   └── nsa-mcp-hub（聚合；639 个工具）
         ├── sw        205   SolidWorks 2025
         ├── acad       55   AutoCAD 2025
         ├── ug         89   UG NX 2512（CAM / 机床 / 钣金 / 装配约束，需 .NET 桥）
         ├── nx         66   UG NX 2512（journal 建模 / 装配 / 制图）
         ├── catia      57   CATIA V5（本机未装，验收 SKIP）
         ├── codesys    60   CODESYS 3.5（常驻服务，免 COM）
         ├── gx         47   GX Works3
         ├── autoshop   42   汇川 AutoShop V4.11
         └── eplan      17   EPLAN 2.9（只读）
        （+1 个 nsa_hub_status = 639）
```

**统一契约**：`{ok, kit, capability, reads, checks, errors, seconds}`；
`ok = ok and all(checks) and not errors` —— 不看 API 返回值、不看退出码、不看 stderr。
判据来源：几何量测（体积/面积/包围盒/孔径）、读数回读（尺寸/配置/材料）、数学恒等式
（齿轮 `da=m(z+2)`、体积=面积×高）、编译诊断计数、结构性字段校验。

---

## 2. 各 kit 现状

| kit | 工具 | 需要的应用/服务 | 最近一次验收证据 | 已知限制（详见各仓 `docs/UNSUPPORTED.md`） |
|---|---|---|---|---|
| **sw** | 205 | SolidWorks 2025（须已在跑，验收**不会**替你启动） | 2026-11-06 全绿；2026-11-07 后新增工具待纳入 | 孔向导 `HoleWizard5` 在 COM 下不建特征（螺纹孔改走 `sw_threaded_hole`）；`CreateDrawViewFromModelView3` 建的视图**无几何**（工程图不可交付）；`InsertProtrusionSwept4`/AddComponent5 签名坑见 `docs/PITFALLS.md` |
| **acad** | 55 | AutoCAD 2025，**必须** `<<VANILLA>>` 配置 | 2026-11-06 全绿（55/55） | 需 `ATTDIA=0`、`FILEDIA` 妥善设置（否则属性/文件对话框卡死）；块属性、三维布尔有已知上限见 `docs/UNSUPPORTED.md` |
| **ug** | 89 | NX 2512 + `.NET` 桥（`dotnet_bridge`）；两套会话：标准库 / 阴影库 | 2026-11-06：21/22 PASS + 1 SKIP（`machine_swap` 阴影库下跳过） | **ISV 动态播放不可用**（`PlayForward` 在 `Session.Execute` 里不返回，实测 >600 s）；机床撞刀/轴限改做**静态几何判定**；`machine_validate` 会话敏感，跑前要换干净会话 |
| **nx** | 66 | NX 2512（nxkit 会自己拉起） | 2026-11-06 全绿（66/66） | 见 `nxkit/docs/UNSUPPORTED.md`：草图/Drafting 部分能力仅 journal 级 |
| **catia** | 57 | CATIA V5（**本机未装**） | 未做过真机验收（SKIP） | 仅到契约级；建模/曲面/Analysis 工具面已备好，装机后需重跑验收 |
| **codesys** | 60 | CODESYS 3.5 + codesyskit 常驻服务（headless，自动起） | 2026-11-06 全绿（60/60） | 必须建 Task 才真编译；编译诊断在 stderr；`--profile` 路径要带引号（见 `codesyskit/docs/PITFALLS.md`） |
| **gx** | 47 | GX Works3（会前台抢焦点） | 2026-11-06 全绿（47/47） | 无 COM，必须前台激活；未转换不给存盘；XML 标签放错位置会被静默忽略 |
| **autoshop** | 42 | AutoShop V4.11（MFC，抢焦点） | 2026-11-06 全绿（42/42） | 只能读 `.hcp`/`.LD`/H5U IL 与写 H3U 指令表；在线/下载未打通（见 `autoshopkit/docs/UNSUPPORTED.md`） |
| **eplan** | 17 | EPLAN 2.9 已打开工程 | 2026-11-06：7 条只读用例通过 | **只读**；设计写入/验收被禁用（construction 释放关闭） |

**覆盖度口径（重要）**：`docs/acceptance-coverage.md` 是"**现存 `_runs` 报告里能查到的证据**"的并集，
不是代码能力上限。`_runs` 只保留最近 30 份报告，所以**历史 100%（626/626，2026-11-06）无法靠翻旧报告复现**——
需要重跑一次才有同等证据。2026-11-06 之后 sw 增加了 12 个工具（193 → 205），这批新工具尚未纳入验收证据。

当前实测工具面 **638 + 1 = 639**（比 11-06 的 626 多 13：sw 新增 12 + hub 层 1）。

---

## 3. 怎么跑

```powershell
$py = "C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = "D:\bililive\nsa-mcp-hub"

# ① 全量收官（自动探测哪些应用开着 → 只跑能跑的 → 最后重算覆盖表）
.\scripts\run_all.ps1

# ② 带上"重"组（nx 会拉起 NX、gx/autoshop 会抢焦点）
.\scripts\run_all.ps1 -IncludeHeavy

# ③ 单 kit / 单用例
& $py -m nsa_mcp_hub.acceptance --kit sw
& $py -m nsa_mcp_hub.acceptance --kit ug --only ug.flow.machine_kit_bind

# ④ 只跑内核单测（不需要任何软件）
.\scripts\ci.ps1 -SkipAcceptance
```

`run_all.ps1` 会为每个 kit 单独写报告（`_runs/acceptance-<时间戳>.json`），最后打印汇总表；
任一 kit 出现 FAIL/ERROR 时退出码非 0，可直接接计划任务。

---

## 4. 环境坑（会话级，跑之前先看）

1. **锁文件**：`%TEMP%\nsa-mcp-hub-<kit>.lock`；有残留会让后续调用全部"拿不到锁"，
   删掉锁并杀掉对应的 `python -m nsa_mcp_hub.servers.<kit>_mcp` 进程即可。
2. **NX 双会话**：标准库会话（`ugraf.exe` 直接起）只认库机床；自家 `.mtk` 必须用
   `MCP/UG/scripts/start-nx-shadow.ps1`（带四个 `UGII_CAM_LIBRARY_*` 环境变量）。
   切换前必须先杀掉 `ugraf.exe`，否则会话被污染（`MOM_TCL：用户选择了中止`）。
3. **NX `machine_validate`**：该用例会**重启 NX** 换干净会话（会话一脏它就挂），因此它必须是 ug 最后一条用例。
4. **SW 全量前先关掉 SolidWorks 里的测试文档**：`sw.flow.inspect` 在多文档时会 600 s 超时。
5. **AutoCAD 配置**：必须 `<<VANILLA>>`（`(getvar "CPROFILE")` 要等于 `<<VANILLA>>`，不是 `<<ACADE>>`）。
6. **不要为跑验收去启动应用**：除 nxkit（自己拉 NX）和 codesys（headless 服务）外，其余 kit 一律"应用没开就 SKIP"。

---

## 5. 收官判定清单

- [x] 9 个 kit 统一契约与判据，`ok` 只由 checks/errors 决定
- [x] 每个 kit 有 `docs/UNSUPPORTED.md` 明确列出"不可用/曾假通过"的能力
- [x] 假通过已被清掉（`sw_hole_wizard` 孔径反算、ug 播放工具已撤、codesys 必须读编译日志）
- [x] 一键收官脚本 `scripts/run_all.ps1`（自动探测 + 汇总 + 覆盖重算）
- [x] 仓库干净、可复现（hub / swkit / acadkit / nxkit / gxkit / codesyskit / autoshopkit 均已提交）
- [ ] **重跑一次 `run_all.ps1` 把 639 个工具的证据补齐**（当前 `_runs` 只剩最近 30 份报告）
- [ ] CATIA 装机后再补真机验收（现在只有契约级）
- [ ] NX ISV 动态播放：需 UI 自动化驱动，已明确不做

---

## 6. 维护约定

- 新增/修改工具 → 改 registry 里的证据字段 + 跑对应 kit 验收 + `scripts/coverage_report.py --write`
- 发现"调用成功但几何没变"→ 先补判据，再谈修复（本项目最常见的坑）
- 每个 kit 的 `docs/UNSUPPORTED.md` 是"不可用清单"的**唯一权威**，文档漂移优先修它
