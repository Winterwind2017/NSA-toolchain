"""eplan 适配器：把 CAD_SERVERS_HOME 的 EPLAN 2.9 native MCP（67 个工具）代理进统一内核。

服务端这块覆盖的是电气设计侧：**工程/页/功能**读取、**符号与部件库**检索、
**native snapshot / intent 审图**、**trial 写操作**（只在固定的可丢弃工程内）、
以及本地 SDK/帮助检索。

前置条件（服务端要求）：
1. 本机装了 EPLAN 2.9（本机：`C:\\Program Files\\EPLAN\\Common`，`EPLAN Client Service` 在跑）；
2. 想读真实工程时要有 bridge 进程（`eplan_bridge_discover` 能列出实例）；
   没有 bridge 时**只读工具仍可用**，只是 projects/pages 那些会返回不可用；
3. `EPLAN_MCP_WORKSPACE` 指到工作目录（可选，缺省用服务端默认），
   `EPLAN_MCP_PROFILE` 默认 `review`（只读）；写操作只在 `trial` 且固定工程内允许。
"""

from __future__ import annotations

import os

from .proxymcp import build_proxy_kit, venv_python

KIT_KEY = "eplan"
KIT_NAME = "CAD_SERVERS_HOME EPLAN 2.9 MCP（工程·页·符号·审图）"
HUB = os.environ.get("CAD_SERVERS_HOME", os.path.expanduser(r"~\cad-servers"))
EPLAN_DIR = os.path.join(HUB, "MCP", "EPLAN")

INSTRUCTIONS = (
    "eplan：EPLAN 2.9 的电气设计工具面（代理 CAD_SERVERS_HOME 的 EPLAN MCP）。"
    "覆盖工程/页/功能的只读读取、符号与部件检索、native snapshot 与 design-intent 审图、"
    "以及限定在可丢弃 trial 工程内的写操作。"
    "调用前先 eplan_diagnostics 看 EPLAN 与 bridge 状态；返回统一为 {ok,reads,checks,errors}。"
)


def build_kit():
    # 优先 MCP/EPLAN/.venv（mcp>=1.27.1 + jsonschema），退回共享 CAD_SERVERS_HOME/.venv
    py = venv_python(EPLAN_DIR, HUB)
    argv = [py, "server.py"]
    env_extra = {
        "PYTHONPATH": EPLAN_DIR + (os.pathsep + os.environ["PYTHONPATH"]
                                  if os.environ.get("PYTHONPATH") else ""),
        "EPLAN_MCP_PROFILE": os.environ.get("EPLAN_MCP_PROFILE", "review"),
    }
    return build_proxy_kit(
        key=KIT_KEY, name=KIT_NAME, argv=argv, cwd=EPLAN_DIR,
        env_extra=env_extra, instructions=INSTRUCTIONS, prefix="eplan",
        timeout_s=900.0,
        prelude="EPLAN MCP 起不来（检查 CAD_SERVERS_HOME/MCP/EPLAN 与 mcp/jsonschema/pywin32）",
    )
