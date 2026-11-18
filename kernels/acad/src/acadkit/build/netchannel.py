"""走 .NET 插件（进程内通道）的两条能力：`solid.revolve` / `layer.state`。

背景：这两条在 ActiveX/命令行里都做不到（`AddRevolvedSolid` 报"输入无效"，
`-LAYERSTATE` 会永久卡在命令提示符）。它们只在**进程内托管代码**里可用，
所以由 `dotnet/AcadKit.Plugin.dll` 提供命令，这里只负责"发命令 + 拿证据"。

插件把结果写成图面上一行 MText（`AKRESULT <tag>: ...`），
所以判据仍走 acadkit 既有的读回通道，不解析命令行文本。

前置：插件必须先部署（`python tools/netload.py --deploy`）。
部署是持久的（安装目录 + 注册表），AutoCAD 每次启动自动加载。
没部署时本文件的 build 不会假装成功——命令会"未知命令"，判据拿不到实体从而失败。
"""

from __future__ import annotations

import time
from typing import Any, Dict

from ..core import com


def _send(doc: Any, line: str, settle: float = 1.0) -> None:
    com.retry(lambda: doc.SendCommand(line), label="SendCommand(%r)" % line[:24])
    time.sleep(settle)


def build_revolve(doc: Any, ctx: Dict[str, Any]) -> None:
    """让插件用 CreateRevolvedSolid 建一个空心圆柱（绕 Y 轴整圈）。"""
    _send(doc, "ACADKITREVOLVE\n", settle=1.5)
    ctx.setdefault("artifacts", {})["revolve_cmd"] = "ACADKITREVOLVE"


def build_layer_state(doc: Any, ctx: Dict[str, Any]) -> None:
    """让插件做一次 图层状态 保存→改色→恢复 的完整循环。"""
    _send(doc, "ACADKITLAYERSTATE\n", settle=1.5)
    ctx.setdefault("artifacts", {})["layerstate_cmd"] = "ACADKITLAYERSTATE"
