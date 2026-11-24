"""ug 适配器：把 CAD-Agent-Hub 的 Siemens NX MCP（82 个工具）代理进统一内核。

上游覆盖的是 nxkit 没有的那几块：**CAM**（刀路/后处理/CLSF）、**机床与运动学**
（机床整机、碰撞停止）、**NX 钣金**（tab/flange/bend/展开图）、装配约束写入、
制图注释、交换格式导入、以及 run_python 逃生口。

前置条件（上游要求，缺一条就只能列工具、调不动）：
1. NX 交互式会话在运行，且 `nx_user/startup` 里的 NXMcPRemotingServer.dll 被加载
   （把 `UGII_USER_DIR` 指到 `CAD-Agent-Hub/MCP/UG/nx_user` 即可自动加载）；
2. 上游 `start_mcp.py` 在 NX 里跑过一次，把 socket 桥起来；
   实测最省事的做法：NX 里 **Ctrl+U** 直接加载 `NXMcPRemotingServer.dll`
   （或跑 `start_bridge.py`），然后保持 NX 开着。桥没起时的报错原文是
   "cannot reach the non-blocking NX bridge at http://127.0.0.1:48161/NXOpenSession"。
3. 本机 NX 有对应模块许可（CAM 需要 CAM 许可）。
"""

from __future__ import annotations

import os

from .proxymcp import build_proxy_kit, venv_python
from .. import paths

KIT_KEY = "ug"
KIT_NAME = "CAD-Agent-Hub UG/NX MCP（CAM·机床·钣金）"
HUB = os.environ.get("CAD_AGENT_HUB") or paths.CAD_AGENT_HUB
UG_DIR = os.path.join(HUB, "MCP", "UG")

INSTRUCTIONS = (
    "ug：Siemens NX 的扩展工具面（代理 CAD-Agent-Hub 的 NX MCP）。"
    "与 nxkit 的分工：nxkit 负责建模/草图/曲线/曲面/布尔/测量/装配插入/工程图/导出；"
    "本 kit 补 CAM（刀路、后处理、CLSF）、机床与运动学仿真、NX 钣金与展开图、"
    "装配约束写入、制图注释、交换格式导入、run_python。"
    "调用前先 ug_ping 确认桥在。返回统一为 {ok,reads,checks,errors}。"
)


def build_kit():
    # 优先 MCP/UG/.venv（mcp==1.26.0），退回共享 CAD-Agent-Hub/.venv
    py = venv_python(UG_DIR, HUB)
    # 注意：mcp_server.py 只是 3 个工具的雏形；完整的 82 个在 server.py
    argv = [py, "server.py"]
    env_extra = {
        "PYTHONPATH": UG_DIR + (os.pathsep + os.environ["PYTHONPATH"]
                                if os.environ.get("PYTHONPATH") else ""),
        "NX_MCP_ALLOW_EXECUTE": os.environ.get("NX_MCP_ALLOW_EXECUTE", "1"),
    }
    return build_proxy_kit(
        key=KIT_KEY, name=KIT_NAME, argv=argv, cwd=UG_DIR, env_extra=env_extra,
        instructions=INSTRUCTIONS, prefix="ug", timeout_s=1800.0,
        prelude="UG MCP 起不来（检查 MCP/UG/.venv 或 CAD-Agent-Hub/.venv 是否有 mcp 包）")
