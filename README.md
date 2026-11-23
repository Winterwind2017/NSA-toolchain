# nsa-toolchain —— 非标自动化工具链（monorepo）

> **NSA = Non-standard automation（非标自动化）**。这个仓库把原先分散的一堆小仓收成一处：
> **6 个软件自动化内核 + 聚合网关 + 6 个 agent 技能**。
> 每个内核仍然绑定各自的软件版本与许可证（AutoCAD 2025 / SolidWorks 2025 / NX 2512 /
> GX Works3 / CODESYS 3.5 / AutoShop V4.11），只是不再各占一个仓库。

## 目录

```
kernels/
  sw/          SolidWorks 2025         （原 solidworks-agent-kit，swkit）
  acad/        AutoCAD 2025            （原 autocad-agent-kit，acadkit）
  nx/          UG NX 2512              （原 nxkit）
  gx/          GX Works3               （原 gxkit）
  codesys/     CODESYS 3.5             （原 codesyskit）
  autoshop/    汇川 AutoShop V4.11      （原 autoshopkit）
hub/           聚合网关 nsa-mcp-hub（MCP 端点、验收 runner、覆盖报告、run_all.ps1）
skills/        6 个域技能 + 1 个路由技能 nsa-toolchain/（先看它决定加载哪个域）
docs/          仓库级文档（仓库地图、收官说明、迁移记录）
scripts/       仓库级脚本（迁移/校验）
```

## 每个内核仍然是「库 + CLI + MCP」

| 内核 | 软件 | 入口 | 文档 |
|---|---|---|---|
| `kernels/sw` | SolidWorks 2025 | `python -m swkit.mcp.server` | `kernels/sw/docs/` |
| `kernels/acad` | AutoCAD 2025 | `python -m acadkit...` | `kernels/acad/docs/` |
| `kernels/nx` | NX 2512 | `python -m nxkit...` | `kernels/nx/docs/` |
| `kernels/gx` | GX Works3 | `python -m gxkit...` | `kernels/gx/docs/` |
| `kernels/codesys` | CODESYS 3.5 | 常驻服务 + CLI | `kernels/codesys/docs/` |
| `kernels/autoshop` | AutoShop V4.11 | `python -m autoshopkit.cli` | `kernels/autoshop/docs/` |

统一由 `hub/` 聚合成**一个 MCP 端点**（`python -m nsa_mcp_hub.servers.nsa_hub_mcp`），
统一返回结构 `{ok, kit, capability, reads, checks, errors, seconds}`，`ok` 只由 `checks` + `errors` 决定。

## 常用命令

```powershell
$py = "C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = "D:\bililive\nsa-toolchain\hub"

# 聚合网关（MCP，stdio）
& $py -m nsa_mcp_hub.servers.nsa_hub_mcp

# 一键收官：探测已开的应用 → 只跑能跑的 kit → 汇总 + 覆盖重算 + 证据归档
.\hub\scripts\run_all.ps1

# 单 kit 验收
& $py -m nsa_mcp_hub.acceptance --kit sw

# 技能一致性（路由覆盖 + 快照↔注册表 + 每个技能自带检查）；CI 里也会跑
& $py scripts\check_skills.py --check
```

## 技能层（给 agent 的"脑子"）

内核是**手**（能执行、有判据），技能是**脑子**（什么时候用、有什么坑、怎么算做成）：

- `skills/nsa-toolchain/` —— **路由**：只回答"用哪个域、什么顺序、怎么判"，不执行任何操作；
- `skills/ww-*/` —— 6 个域技能，各自带 `capabilities.json` 快照与 `tools/check_skill.py`；
- `skills/*/SKILL.md` 里出现的每个能力 id 都必须存在于对应内核的注册表，
  由 `scripts/check_skills.py` 核对：**内部矛盾（FAIL）**与**跨仓版本漂移（WARN，`--strict` 升级为 FAIL）**分开报。
- 没有 `docs/registry.yaml` 的内核（sw / autoshop / codesys）会被明确标成"**无法核对**"，不会假装通过。

## 离线能力（不需要开 CAD 软件）

| 模块 | 能做什么 | 判据 |
|---|---|---|
| `kernels/acad/src/acadkit/dfm/` | 钣金/铣削/注塑/3D 打印的**可制造性检查**，每条给「改哪儿」 | 合规件零告警；违规件命中对应规则（17 例） |
| `kernels/acad/src/acadkit/brep/` | 参数化件（轴/法兰/板）→ 真 B-rep → STEP/STL（cadquery/OCP） | 体积与解析式一致（≤1e-6）；STEP 读回体积一致（10 例） |
| `kernels/acad/src/acadkit/fea/` | 五种工况 screening（gmsh 划网格 → Abaqus inp → CalculiX ccx）：轴向拉伸（矩形/圆）、悬臂梁、圆轴扭转、四边简支板 | 默认二阶四面体 C3D10；实测悬臂 5.3e-4、扭转 2.9e-3、板 3.9e-2、矩形拉伸 5e-8、圆轴 7.1e-4；反力合力 = 外载（25 例） |
| `scripts/doctor.py` | 一条命令报 6 个内核的包/引擎/进程/技能 + FEA 三环（gmsh/sfepy/skfem/ccx） | 查不到的标 `SKIP`，不假装通过；退出码 = 阻塞数 |
| `scripts/install_skills.py` | 把 7 个技能（含路由）装到目标 skills 根，支持 `--dry-run` / `--update` | 装完 `check_skills.py` 通过；`--update` 只覆盖清单登记的两个文件 |

## 历史与发布

- 各内核的历史通过 `git subtree` 完整保留（提交作者/时间不变），仍可 `git log -- kernels/sw` 查看。
- 独立发版用 **tag 前缀**：`sw-v1.2.0` / `acad-v0.9.0` / `hub-v0.16.0` …
- 原来的单仓已归档（GitHub archive，只读可查），内容与历史都已并入本仓。

## 本地路径说明（Windows）

迁移后 `D:\bililive\{solidworks-agent-kit,acadkit,nxkit,gxkit,codesyskit,autoshopkit,nsa-mcp-hub,ww-*}` 
都是指向本仓对应子目录的**目录联接（junction）**，老路径继续可用（环境变量、脚本、MCP 配置都不用改）。
新建路径请优先用 `D:\bililive\nsa-toolchain\...`。
