# QUICKSTART —— 10 分钟跑起来

本仓库是「**库 + CLI + MCP**」的工具链：6 个 CAD/PLC 自动化内核 + 一个把它们聚合成单一 MCP 端点的 hub + 给 agent 用的技能。

**两条路线**：

- **A. 离线路线（不装任何 CAD 软件，5 分钟）** —— 跑可制造性检查、出三视图/图纸、FEA、技能一致性检查。适合先看价值。
- **B. 真机路线** —— 驱动本机已装的 AutoCAD / SolidWorks / NX / GX Works3 / CODESYS / AutoShop。需要 Windows + 对应软件 + 许可证。

---

## A. 离线路线

### 1. 前置

- Python **3.10+**（3.12 推荐）
- Git
- 任意目录即可（路径不用带 `nsa`，全仓库没有写死路径）

```bash
git clone https://github.com/Winterwind2017/NSA-toolchain.git
cd NSA-toolchain
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate        # Linux / macOS / Git Bash
pip install -r requirements-dev.txt
```

> Linux/macOS 上 `requirements.txt` 里的 `pywin32` 会自动跳过（`sys_platform == "win32"` 标记）。

### 2. 自检

```bash
python scripts/doctor.py
```

预期：Python / 依赖 / 内核包 / 技能目录逐条给 `OK` / `WARN` / `SKIP`。
**没装 CAD 软件时，引擎那几行是 `WARN`（不是失败）**；退出码 = 阻塞项数量，0 表示可以继续。

### 3. 跑一个离线能力（不需要 AutoCAD）

```bash
# 1) 可制造性检查（纯规则，零额外依赖）：钣金/铣削/注塑/3D 打印，每条给"改哪儿"
PYTHONPATH=kernels/acad/src python -c "from acadkit.dfm.rules import check_sheet_metal; print(check_sheet_metal(thickness=1.5, bend_radius=0.8))"

# 2) 选型计算（纯 Python，零额外依赖）：500 N、0.5 MPa、中速 → 标准缸径
# Windows PowerShell：$env:PYTHONPATH = "design"
PYTHONPATH=design python -c "from design_calc import cylinder; print(cylinder.select_bore(500, 0.5, 'medium'))"

# 3) 技能一致性（路由覆盖 + 快照 ↔ 注册表）
python scripts/check_skills.py --check
```

第 1 条会打印 `Report(process=..., findings=[Finding(rule=..., severity=..., fix=...)])`。

想再看出图（三视图 PNG / 矢量 PDF）需要 B-rep 后端，装一次即可（体积较大）：

```bash
pip install "cadquery>=2.4"        # 或 pip install -e "kernels/acad[brep]"
python scripts/nsa.py drawing --part flange --outer 120 --title 法兰盘 --number NSA-001 --pdf flange.pdf
```

Windows 上直接 `python scripts/nsa.py drawing ...` 也能用（会调用本机已装的 AutoCAD）；
没有 AutoCAD 但装了 cadquery 时走离线 B-rep，同样能出图。

### 4. 跑测试（与 CI 一致）

```bash
pip install pytest
(cd kernels/acad && python -m pytest tests/test_docs.py tests/test_reports.py tests/test_offline.py -q)
PYTHONPATH=hub python -m pytest hub/tests -q
python -m pytest scripts/tests -q
```

---

## B. 真机路线（Windows）

### 1. 装软件

| 内核 | 软件 | 版本（实测） |
|---|---|---|
| `kernels/acad` | AutoCAD | 2025（`<<VANILLA>>` 配置） |
| `kernels/sw` | SolidWorks | 2025 |
| `kernels/nx` | UG NX | 2512 |
| `kernels/gx` | MELSOFT GX Works3 | 当前版（FX5U / iQ-R） |
| `kernels/codesys` | CODESYS Development System 3.5 | SP22 Patch 2 |
| `kernels/autoshop` | 汇川 AutoShop | V4.11 |

每个软件都要有**可自动化调用的许可证**（COM/ActiveX/脚本引擎），并以当前用户身份能正常打开。

### 2. 环境变量（都可选，不设就用默认安装路径）

```powershell
$env:NSA_PYTHON    = "C:\Python312\python.exe"   # 指定解释器
$env:NSA_ACAD_EXE  = "C:\Program Files\Autodesk\AutoCAD 2025\acad.exe"
$env:NSA_SW_EXE    = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe"
$env:NSA_CCX       = "C:\tools\calculix\ccx_i4_static.exe"
$env:NSA_CAD_VIEWER= "D:\path\to\cad-viewer\scripts\viewer"
```

完整清单见 [`hub/nsa_mcp_hub/paths.py`](hub/nsa_mcp_hub/paths.py) 顶部注释。

### 3. 单内核冒烟

```powershell
$env:PYTHONPATH = "$PWD\hub"
python -m nsa_mcp_hub.acceptance --kit codesys      # 换成 sw / acad / nx / gx / autoshop
```

输出是统一结构 `{ok, kit, capability, reads, checks, errors, seconds}`；
`ok` 只由 `checks` 与 `errors` 决定——**没有"看起来成功"这种状态**。

### 4. 接进你的 agent（MCP）

hub 是一个标准 stdio MCP server：

```
命令: python -m nsa_mcp_hub.servers.nsa_hub_mcp
环境: PYTHONPATH=<仓库>/hub
```

Windows 下也有免配置启动器（相对路径，无写死盘符）：

```
hub/_tools/nsa-mcp-hub.cmd            # 聚合端点（9 个 kit、600+ 工具）
hub/_tools/nsa-mcp-hub-acad.cmd       # 只挂 AutoCAD（54 个工具）
```

各客户端（Claude Desktop / Cursor / Codex / DSH）的完整配置片段见 [`docs/MCP-SETUP.md`](docs/MCP-SETUP.md)。

### 5. 装技能（给 agent 的"脑子"）

```bash
python scripts/nsa.py skills install --target <你的 skills 根目录>
python scripts/nsa.py skills status  --target <你的 skills 根目录>   # fresh / 旧版 / 被改 / 未装
```

技能只写「什么时候用、有什么坑、怎么算做成」，不重复内核文档。

---

## 常见问题

**Q: 没有 CAD 软件能用吗？**
能跑离线部分：DFM 检查、B-rep/STEP、三视图与图纸 PDF、FEA（需 ccx）、cad-viewer、技能校验。
真机能力（建模/装配/出图到 AutoCAD 等）必须有对应软件。

**Q: Linux 能用吗？**
离线部分可以（CI 就跑在 ubuntu 上）；真机部分依赖 Windows COM/UIAutomation，需要 Windows。

**Q: 端口/服务？**
本仓库不起后台服务。MCP 是 stdio 进程，由客户端按需拉起。

**Q: 为什么有 `kernels/` 和老仓库名？**
2026-11 把 13 个独立仓合并成一个 monorepo，历史用 `git subtree` 完整保留（`git log -- kernels/sw` 可查）。
