# 变更记录

> 只记"对外可见口径"的变化（工具面、判据口径、验收基线）。逐条实现细节看 `git log`。

## v1.4.2 —— 2026-11-25（整圆圆角）

本机 SolidWorks 2025（33.4.1）：

- 80×20×30 的板做整圆圆角，体积从 48000 mm³ 降到 44566.37 mm³。
- 选面标记是侧面 2、中间面 512、另一侧面 4。`FeatureFillet3` 的类型是 3，选项是 0。

## v1.4.1 —— 2026-11-25（筋、弹簧、双半径圆角、投影带记号）

本机 SolidWorks 2025（33.4.1）：

- 三角形筋：体积 12000 mm³，与 ½×30×20×40 一致。原生 `InsertRib` 仍返回 0。
- 弹簧：螺旋线扫描，体积 669.83 mm³。
- 两条边 2 mm 和 5 mm：两次体积都下降。单边可变半径会断开 COM，没有采用。
- 图纸公共基准读回 `A-B`，投影带记号 `P` 读回。框下毫米高度接口返回 False。

整圆圆角换了选面标记，体积仍然不变。

## v1.4.0 —— 2026-11-25（补齐对方缺口中的可验证项）

清单见 `docs/CAPABILITY_GAP.md`。

本机做成并读回体积的：

- 直齿轮：m=2、z=12、厚 8 mm，体积 4079.97 mm³
- 近似链轮：12 齿、节距 12.7 mm、厚 6 mm，体积 12442.06 mm³

离线补上并有测试的：假成功门禁、孔表、公差文字、改名预览、中文文字检查、STL、预览页、边长筛选、螺旋线长度、运动采样是否可交付。

仍未验证：筋、可变半径圆角、投影公差带、弹簧实体、CAD Studio 桌面程序。

## v1.3.3 —— 2026-11-25（结构构件规格）

`InsertStructuralWeldment` 本身不能选规格。构件生成后，用
`IStructuralMemberFeatureData.ConfigurationName` 写回并重建。

本机 ISO 方管、300 mm 直线：

- `20 x 20 x 2`：体积 40109.7 mm³，配置名读回一致
- `40 x 40 x 4`：体积 160438.9 mm³，配置名读回一致
- `99 x 99 x 9`：不算通过

## v1.3.2 —— 2026-11-25（结构构件）

线段数组传给 `StructuralMemberGroup` 会在 COM 边界丢掉。
改为 `Select4` 选中草图线段，再调用没有数组参数的 `InsertStructuralWeldment`。

本机 SolidWorks 2025（33.4.1），ISO 方管默认配置：
特征 `WeldMemberFeat`，体积 40109.7 mm³。

## v1.3.1 —— 2026-11-25（焊件轮廓库定位）

本机本来就有 SolidWorks 焊件轮廓，路径是
`%ProgramData%\SOLIDWORKS\SOLIDWORKS 2025\weldment profiles`。
之前没去读它，所以误判成没有库文件。

- `weldment_library.default_profile()` 优先 ISO 方管，其次 GB 方钢、ANSI 方管。
- ISO 方管读到的配置：`20 x 20 x 2`、`30 x 30 x 2.6`、`40 x 40 x 4`、`80 x 80 x 5`。
- 不把 SolidWorks 自带轮廓复制进仓库。

## v1.3.0 —— 2026-11-25（焊件特征与窗口预览）

本机 SolidWorks 2025（33.4.1）复跑：

- `sw_insert_weldment`：comtypes 调用 `InsertWeldmentFeature`，特征树出现 `WeldmentFeature`。
- `sw_preview_frame` / `sw_preview_burst`：只抓 `SLDWORKS.exe` 窗口，两帧 BMP 均写出。不抓桌面。

仍未通过，保持 `unverified`：

- `sw_rib`：`InsertRib` 返回 0，体积不变。
- `sw_gtol_frame`：框值读写已编码；本机类型库没有投影公差带。
- `sw_structural_member`：要真实轮廓文件，这次没有可用的库文件。

`advanced.py` 不再返回写死的方管切割清单。

## v1.2.0 —— 2026-11-25（驱动复核、齿廓、交付门禁）

独立实现，不引入外部仓库的代码。hub 工具面未改，`nsa_mcp_hub.__version__` 仍是 `0.2.0`。

- `drive_audit.audit_linear_drive`：丝杠或皮带，复核峰值、RMS、转速、惯量比、斜轴抱闸；丝杠给了直径和长度就核临界转速。
- `gear.involute_xy`：标准直齿渐开线坐标。不生成 SolidWorks 特征。
- `delivery_gate.accept_new_file`：PDF / STEP 必须是本轮新写的，头签名要能对上。

筋特征、焊件和 SolidWorks 2026 形位公差仍未标成已验证。

## v1.1.0 —— 2026-11-25（设计层）

新增，不改变 hub 的工具面，所以 `nsa_mcp_hub.__version__` 仍是 `0.2.0`。

- `design/design_calc`：电机、气缸、丝杆、导轨、减速机、节拍、公差、强度等选型计算。
- `design/knowledge`：非标设计知识库，入口 `design/knowledge/_index.md`。
- 技能 `ww-nsa-design`：七段流程，先算完再交给 CAD / PLC 技能。路由已挂上。
- 离线测试 `design/tests` 守住缸径、负载惯量、丝杆寿命、节拍并联、Goodman 和尺寸链。

## toolchain-v1.0 —— 2026-11-09（13 仓合一）

- 6 内核（sw/acad/nx/gx/codesys/autoshop）+ 本网关 + 6 个技能仓，用 `git subtree`
  收进 monorepo `NSA-toolchain`，历史完整保留（521 提交 / 563 tracked 文件）。
- 老路径全部改为目录联接，环境变量与 MCP 配置不用改；旧 GitHub 仓全部归档（只读）。
- 动机：13 个仓加起来才 3 MB，但 10 个脚手架文件在 ≥4 个仓里各存一份且内容不同
  （实例：tool-surface.md 写 579 工具、实际 639），6 个技能仓各复制一套 tools/ 脚本且哈希全不同。
- 配套：`docs/MIGRATION.md`（迁移记录；迁移脚本只在作者本地留档，不随仓库发布）。

## v1.0-acceptance —— 2026-11-09（收官里程碑）

**口径**：9 个 kit、**639 个工具**（638 kit 内 + 1 个 `nsa_hub_status`），统一契约
`{ok, kit, capability, reads, checks, errors, seconds}`，`ok` 只由 `checks` + `errors` 决定。

新增：

- `docs/RELEASE.md` —— 收官说明：各 kit 现状 / 已知限制 / 怎么跑 / 环境坑 / 收官清单。
- `scripts/run_all.ps1` —— 一键收官：探测已开应用 → 只跑能跑的 kit（未开就 SKIP 并写原因）→
  逐 kit 报告 → 汇总表 → 重算覆盖表 → 把本次报告归档到 `_archive/acceptance-<时间戳>/`。
  参数：`-IncludeHeavy`（连 nx/ug/gx/autoshop）、`-Kits`、`-SkipUnit`、`-NoCoverage`、`-NoKeepEvidence`。
- `docs/acceptance-coverage.md` 增加**口径提醒**：表格统计的是 `_runs/` 现存报告的证据，
  报告被轮转后数字会掉，属"证据缺失"而非能力回退；历史 100% 基线需重跑复现。

修复：

- `codesys.flow.ops` 改成**自给自足**：原来它依赖"上一个剧本留下的工程里存在 `AccPlay`"，
  用例顺序一变（`codesys.flow.objects` 会新建自己的工程）就 `E_STATE: path segment 'AccPlay'
  not found`。现在自己建工程 + 建 POU + 写实现。实测 codesys **17/17 通过（28.1 s）**。

验收基线（本机、2026-11-09）：

| kit | 结果 | 说明 |
|---|---|---|
| codesys | **17/17 PASS**（28.1 s） | headless，无需 GUI |
| 其余 8 个 kit | SKIP | 对应应用未运行（收官脚本如实跳过，不假装通过） |

> 历史基线：2026-11-06 曾在 626 个工具时跑出 **626/626 = 100%**（含 ug 21/22+1SKIP、
> sw/acad/nx/gx/codesys/autoshop 全绿）。之后 sw 增加 12 个工具、hub 层 +1，
> 覆盖证据需要重跑才有同等效力。

## 之前的主要版本（摘）

- **v0.15.x** —— 装配图国标 A3 图框 + 六列 BOM 表 + 标题栏填充；BOM 代号规则（图号优先/类型编码）；
  工程尺寸两段扫描 + 轴孔目标；可见性守卫（私有仓断言）。
- **v0.14.x** —— BOM 表与标题栏栏位填充落地。
- **更早** —— 六 kit 合并进单内核（统一契约/单飞锁/超时守卫/幂等 `request_id`/`kit_runtime`），
  随后补入 `ug`（NX MCP 代理，CAM/机床/钣金）与 `catia`（V5 MCP 代理）、`eplan`（只读）。
