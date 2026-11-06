# 被代理 server 的独立 venv

## 为什么要拆

三个被代理的 CAD MCP server 对 `mcp` SDK 的版本要求**互斥**：

| kit | server 目录 | 依赖 |
|---|---|---|
| `ug` | `CAD-Agent-Hub/MCP/UG` | `mcp==1.26.0`（镜像上的 1.27.1 会拉不兼容的 `mcp-types 2.0.0`） |
| `eplan` | `CAD-Agent-Hub/MCP/EPLAN` | `mcp>=1.27.1,<2` + `jsonschema>=4.25,<5` + `pywin32>=306` |
| `catia` | `CAD-Agent-Hub/MCP/CATIA` | `mcp>=1.7,<3` + `pywin32>=305` |

共用 `CAD-Agent-Hub/.venv` 时只能满足其中一个，且任何一次升级/冲突会同时影响三款软件。

## 现在怎么解析

`nsa_mcp_hub/adapters/proxymcp.py` 的 `venv_python(*roots)` **按顺序**找
`<root>/.venv/Scripts/python.exe`，都没有才退回 `sys.executable`：

```python
venv_python(UG_DIR, HUB)        # 先 MCP/UG/.venv，再 CAD-Agent-Hub/.venv
venv_python(EPLAN_DIR, HUB)
venv_python(CATIA_DIR, HUB)
```

所以**建不建都能启动**：没建就沿用共享 venv（旧行为），建了就隔离。

## 建 / 重建

```bat
python scripts\setup_proxy_venvs.py            :: 缺哪个建哪个（幂等）
python scripts\setup_proxy_venvs.py --force    :: 全部删掉重建
python scripts\setup_proxy_venvs.py --only UG  :: 只处理一台
python scripts\setup_proxy_venvs.py --check    :: 只体检，不改文件
```

脚本本体：`scripts/setup_proxy_venvs.py`（用 `CAD-Agent-Hub/.venv` 的解释器跑即可）。

## 验收判据

1. `scripts/setup_proxy_venvs.py --check` → 三台都打印 `python … | <server>\.venv` 且导入成功。
2. 端到端：用 hub 自己的适配器起子 MCP，确认工具面完整（不能出现 `*_unavailable`）：

```python
import sys; sys.path.insert(0, r"D:\bililive\nsa-mcp-hub")
from nsa_mcp_hub.adapters import ug_mcp, eplan_mcp, catia_mcp
for mod, name in ((ug_mcp, "ug"), (eplan_mcp, "eplan"), (catia_mcp, "catia")):
    kit = mod.build_kit()
    names = [t.name for t in kit.tools]
    assert not [n for n in names if n.endswith("_unavailable")], (name, "起不来")
    print(name, len(names))
```

实测（2026-11-06）：`ug` 88、`catia` 56、`eplan` 16（各含 1 个 `*_proxy_tools` 诊断工具）。

## 注意

- 改动只在 **hub 进程下次启动**时生效；正在运行的 hub 仍持有旧的解析结果。
- `MCP/Solidworks` 不是 proxy（`sw` kit 在 hub 进程内跑 `swkit`），不在本文件范围内。
- 共享 venv `CAD-Agent-Hub/.venv` 仍然保留：它是 hub 自身（`mcp` 客户端）和 native kit 的运行环境，不要删。
