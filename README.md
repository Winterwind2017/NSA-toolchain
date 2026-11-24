# NSA-toolchain

**让 agent 能真正操作 CAD / PLC 软件的工具链**：6 个软件自动化内核 + 一个把它们聚合成**单一 MCP 端点**的 hub + 6 个给 agent 的技能。

每个宣称可用的能力都带**判据**（读取什么值、等于什么才算成功）。没有"看起来成功"这种状态。

```
kernels/   sw · acad · nx · gx · codesys · autoshop     6 个内核（库 + CLI + MCP）
hub/       聚合网关：一个端点上挂 9 个 kit、600+ 工具
skills/    1 个路由技能 + 6 个域技能（给 agent 的配方与坑）
docs/      架构 / MCP 接入 / 兼容性
```

NSA = **N**on-**S**tandard **A**utomation（非标自动化）：焊接、铆接压装、上料搬运、冲孔折弯、工装夹具这类设备的建模、出图、编号与 PLC 编程。

## 快速开始

**10 分钟、不装任何 CAD 软件**：

```bash
git clone https://github.com/Winterwind2017/NSA-toolchain.git
cd NSA-toolchain
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python scripts/doctor.py                             # 环境自检（没装 CAD 时引擎行是 WARN，不算失败）
python scripts/nsa.py drawing --part flange --outer 120 --title 法兰盘 --number NSA-001 --pdf flange.pdf
```

第二条会离线生成零件三视图与 PDF 图纸——不需要 AutoCAD。

完整步骤（含真机路线、MCP 接入、技能安装）见 **[QUICKSTART.md](QUICKSTART.md)**。

## 接进你的 agent

hub 是标准 stdio MCP server：

```
命令：python -m nsa_mcp_hub.servers.nsa_hub_mcp
环境：PYTHONPATH=<仓库>/hub
```

Windows 下也可以用免配置启动器（相对路径）：

```
hub/_tools/nsa-mcp-hub.cmd          # 聚合端点
hub/_tools/nsa-mcp-hub-acad.cmd     # 只挂 AutoCAD（工具更少，启动更快）
```

Claude Desktop / Cursor / Codex / DeepSeek Harness 的配置片段见 **[docs/MCP-SETUP.md](docs/MCP-SETUP.md)**。

调用内置的 `nsa_hub_status` 可以确认接好了：

```json
{"hub": "nsa-mcp-hub", "kits_total": 9, "kits_alive": 9, "tools_total": 638}
```

## 统一返回结构

所有工具（包括每个内核的 CLI）返回同一形状：

```python
{
  "ok": True,                     # 只由 checks 与 errors 决定
  "kit": "acad",
  "capability": "geom_circle",
  "reads":  {"area": 706.86},     # 读到的原始值，判据的输入
  "checks": [{"check": "area_eq_pi_r2", "got": 706.86, "want": 706.858, "ok": True}],
  "errors": [],
  "seconds": 0.31,
}
```

agent 只需要看 `ok` 和 `checks`，不用理解每个工具。

## 各内核

| 内核 | 软件 | 实测版本 | 接入方式 | 真机 | 离线 |
|---|---|---|---|---|---|
| `kernels/acad` | AutoCAD | 2025 | COM / ActiveX | ✅ | ✅ DFM、B-rep、图纸、FEA、viewer |
| `kernels/sw` | SolidWorks | 2025 | COM | ✅ | 部分（解析/统计） |
| `kernels/nx` | UG NX | 2512 | `run_journal` + NXOpen | ✅ | 部分 |
| `kernels/gx` | MELSOFT GX Works3 | 当前版 | 工程文件 + UIAutomation | ✅ | ✅ 工程解析 |
| `kernels/codesys` | CODESYS 3.5 | SP22 Patch 2 | 常驻服务 | ✅ | ✅ 工程归档/解析 |
| `kernels/autoshop` | 汇川 AutoShop | V4.11 | 工程文件 + UIAutomation | ✅ | ✅ `.hcp`/`.LD` 解析 |

真机 = 需要 Windows + 该软件 + 可自动化调用的许可证。详见 **[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)**。

## 设计原则

1. **判据优先**：一个能力没有判据就不算实现；判据失败就报失败。
2. **诚实降级**：环境缺失时返回 `SKIP` / `errors`，不假装通过。
3. **离线优先**：能在没有 CAD 的机器上验证的，就放进 CI。
4. **路径可移植**：仓库里不写死本机路径；外部程序用环境变量（见 `hub/nsa_mcp_hub/paths.py`）。

## 开发

```bash
python -m pytest scripts/tests -q
PYTHONPATH=hub python -m pytest hub/tests -q
(cd kernels/acad && python -m pytest tests/test_docs.py tests/test_reports.py tests/test_offline.py -q)
python scripts/check_skills.py --check
```

贡献前请读 **[CONTRIBUTING.md](CONTRIBUTING.md)**。安全相关问题见 **[SECURITY.md](SECURITY.md)**。

## 许可

**MIT**，见 [LICENSE](LICENSE)。第三方来源与商标声明见 [NOTICE.md](NOTICE.md)。

本仓库通过各软件的官方自动化接口驱动你**本机已安装**的软件，与这些厂商无隶属关系；
使用前请确认你的许可证允许自动化调用。
