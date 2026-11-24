"""catia 适配器：把 CAD-Agent-Hub 的 CATIA V5 MCP（55 个工具）代理进统一内核。

覆盖：文档/零件/产品、草图与实体特征（pad/pocket/fillet）、曲面（loft/fill/join/
heal/thick/offset plane/connect curve/boundary/close）、以及 CAD 原生 **Analysis**
（建分析文档 → 加 set/entity/mesh/solution → 绑支撑/材料 → 计算 → 出报告/导数据/截图）。

本机没有装 CATIA V5（2026-11-04 实测），所以这个 kit 只能保证"工具面接得上、
调用会如实报 CATIA 不在"，不能做真机验收。
"""

from __future__ import annotations

import os

from .proxymcp import build_proxy_kit, venv_python
from .. import paths

KIT_KEY = "catia"
KIT_NAME = "CAD-Agent-Hub CATIA V5 MCP（建模·曲面·原生 Analysis）"
HUB = os.environ.get("CAD_AGENT_HUB") or paths.CAD_AGENT_HUB
CATIA_DIR = os.path.join(HUB, "MCP", "CATIA")
SRC = os.path.join(CATIA_DIR, "src")

INSTRUCTIONS = (
    "catia：CATIA V5 的建模/曲面/原生 Analysis 工具面（代理 CAD-Agent-Hub 的 CATIA MCP）。"
    "调用前先 catia_health_check / catia_connect。"
    "注意：本机未安装 CATIA 时，工具会如实返回「CATIA 不可用」，不会假装成功。"
)


def build_kit():
    # 优先 MCP/CATIA/.venv（mcp + pywin32），退回共享 CAD-Agent-Hub/.venv
    py = venv_python(CATIA_DIR, HUB)
    argv = [py, "-m", "catia_mcp.server"]
    env_extra = {
        "PYTHONPATH": SRC + (os.pathsep + os.environ["PYTHONPATH"]
                             if os.environ.get("PYTHONPATH") else ""),
    }
    return build_proxy_kit(
        key=KIT_KEY, name=KIT_NAME, argv=argv, cwd=SRC, env_extra=env_extra,
        instructions=INSTRUCTIONS, prefix=None, timeout_s=1800.0,
        prelude="CATIA MCP 起不来（检查 .venv 是否有 mcp / pycatia）")
