# 兼容性

## 操作系统

| 能力 | Windows 10/11 | Linux | macOS |
|---|---|---|---|
| 离线（DFM 检查、B-rep/STEP、三视图与图纸、cad-viewer、技能校验） | ✅ | ✅（CI 就在 ubuntu 跑） | ✅（未在 CI 覆盖） |
| FEA（需外部 `ccx`） | ✅ | ✅（装 CalculiX） | ✅（装 CalculiX） |
| 真机 AutoCAD / SolidWorks / NX / GX Works3 / AutoShop | ✅（COM / UIAutomation） | ❌ | ❌ |
| 真机 CODESYS / CATIA / EPLAN | ✅ | ⚠️ 未验证 | ⚠️ 未验证 |

> 真机部分依赖 Windows COM、UI Automation 与桌面会话，这是软件本身的限制，不是本项目的选择。

## Python

- 最低 **3.10**，推荐 **3.12**。
- CI 覆盖 3.10 与 3.12。

## 软件版本（实测通过的版本）

| 内核 | 软件 | 版本 | 接入方式 |
|---|---|---|---|
| `kernels/acad` | AutoCAD | 2025（配置 `<<VANILLA>>`） | COM / ActiveX |
| `kernels/sw` | SolidWorks | 2025 SP4.1 | COM（`sldworks.tlb`） |
| `kernels/nx` | UG NX | 2512 | `run_journal` + NXOpen Python |
| `kernels/gx` | MELSOFT GX Works3 | 当前版（FX5U / iQ-R） | 工程文件 + UIAutomation（无 COM） |
| `kernels/codesys` | CODESYS Development System 3.5 | SP22 Patch 2 | 常驻服务（ScriptEngine） |
| `kernels/autoshop` | 汇川 AutoShop | V4.11 | 工程文件 + UI Automation |

其它版本**未经实测**：接口可能改名/移位，工具会返回 `ok:false` 和具体 `errors`，不会假装成功。

## 许可证要求

真机能力要求你拥有对应软件的**可自动化调用许可**（多数商业版包含；教育版/试用版可能受限）。
本项目不提供、不绕过任何许可证。

## 依赖矩阵

| 功能 | 依赖 | 是否必需 |
|---|---|---|
| hub / 各内核 CLI / 技能校验 | `pyyaml` | 必需 |
| Windows 真机（acad/sw/nx/autoshop/gx） | `pywin32` | Windows 必需 |
| FEA 划网格 | `gmsh` | 用 FEA 时必需 |
| FEA 求解 | 外部 `ccx`（CalculiX） | 用 FEA 时必需，设 `NSA_CCX` |
| B-rep / STEP 导出 | `cadquery` + `OCP` | 可选（没有则相关能力标 SKIP） |
| 次级 FEA 后端 | `sfepy`、`skfem` | 可选 |
| 图像/云图 | `matplotlib`（cad-viewer 自带前端） | 可选 |
| 测试 | `pytest`、`numpy` | 开发必需 |

## 离线能力一览（不需要任何 CAD 软件）

| 模块 | 能做什么 |
|---|---|
| `acadkit.dfm` | 钣金 / 铣削 / 注塑 / 3D 打印可制造性检查，每条给"改哪儿" |
| `acadkit.brep` | 参数化件 → B-rep → STEP / STL（需 cadquery） |
| `acadkit.brep.render` | 等轴测 / 三视图 PNG、线框 SVG（需 cadquery + matplotlib） |
| `acadkit.brep.drawing` | HLR 消隐 → 三视图 + 图框 + 标题栏 → 矢量 PDF |
| `acadkit.fea` | 十二种工况：gmsh 划网格 → Abaqus inp → ccx 求解（需 numpy/gmsh/ccx） |
| `scripts/viewer.py` | 起/复用 cad-viewer 看 STEP/STL/GLB/DXF/G-code/URDF/SDF |
| `scripts/check_skills.py` | 技能一致性（路由覆盖、快照↔注册表） |
| `scripts/doctor.py` | 环境自检，逐项 OK/WARN/SKIP |
