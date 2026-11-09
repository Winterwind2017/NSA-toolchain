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
skills/        6 个 agent 技能（原 6 个 ww-* 仓，按目录分开，共享 tools/）
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
```

## 历史与发布

- 各内核的历史通过 `git subtree` 完整保留（提交作者/时间不变），仍可 `git log -- kernels/sw` 查看。
- 独立发版用 **tag 前缀**：`sw-v1.2.0` / `acad-v0.9.0` / `hub-v0.16.0` …
- 原来的单仓已归档（GitHub archive，只读可查），内容与历史都已并入本仓。

## 本地路径说明（Windows）

迁移后 `D:\bililive\{solidworks-agent-kit,acadkit,nxkit,gxkit,codesyskit,autoshopkit,nsa-mcp-hub,ww-*}` 
都是指向本仓对应子目录的**目录联接（junction）**，老路径继续可用（环境变量、脚本、MCP 配置都不用改）。
新建路径请优先用 `D:\bililive\nsa-toolchain\...`。
