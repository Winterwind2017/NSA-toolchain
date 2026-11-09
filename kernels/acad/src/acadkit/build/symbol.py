"""符号类 builder：粗糙度 / 焊接 / 中心线 / 中心标记 / 序号气泡。

官方没有这些 API（`AddBalloon` 不存在），所以都是用基本图元拼的。判据因此
看"图元计数 + 文字内容 + 关键几何"，而不是某个对象的属性。
"""

from __future__ import annotations

import math
from typing import Any, Dict

from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_roughness(doc: Any, ctx: Dict[str, Any]) -> None:
    """GB 粗糙度：尖角两边 + 延长横线 + `Ra 3.2` 文字。"""
    x, y = _p(ctx, "origin", (0.0, 350.0))
    h = float(_p(ctx, "height", 3.5))
    ms = ms_of(doc)
    add(ms, "AddLine", pt(x, y), pt(x - 3, y - 3), label="AddLine")
    add(ms, "AddLine", pt(x, y), pt(x + 3, y - 3), label="AddLine")
    add(ms, "AddLine", pt(x - 3, y - 3), pt(x + 8, y - 3), label="AddLine")
    add(ms, "AddText", "Ra 3.2", pt(x - 2, y + 1), h, label="AddText")


def build_weld(doc: Any, ctx: Dict[str, Any]) -> None:
    """焊接符号：基准线 + 箭头线 + 焊缝尺寸文字。"""
    x, y = _p(ctx, "origin", (0.0, 400.0))
    ms = ms_of(doc)
    add(ms, "AddLine", pt(x, y), pt(x + 30, y), label="AddLine")
    add(ms, "AddLine", pt(x, y), pt(x - 8, y - 8), label="AddLine")
    add(ms, "AddText", str(_p(ctx, "size", "6")), pt(x + 8, y + 1), 3.5,
        label="AddText")


def build_centerline(doc: Any, ctx: Dict[str, Any]) -> None:
    """中心线：两端各超出轮廓 `ext`，线型 CENTER2（不行退回 CENTER）。"""
    x1, y1 = _p(ctx, "start", (0.0, 0.0))
    x2, y2 = _p(ctx, "end", (40.0, 0.0))
    ext = float(_p(ctx, "extend", 2.0))
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    ms = ms_of(doc)
    line = add(ms, "AddLine", pt(x1 - ux * ext, y1 - uy * ext),
               pt(x2 + ux * ext, y2 + uy * ext), label="AddLine")
    linetype = None
    for name in ("CENTER2", "CENTER", "CENTERX2"):
        try:
            doc.Linetypes.Load(name, "acadiso.lin")
        except Exception:                           # noqa: BLE001
            pass
        try:
            line.Linetype = name
            linetype = name
            break
        except Exception:                           # noqa: BLE001
            continue
    ctx.setdefault("artifacts", {})["linetype"] = linetype


def build_centermark(doc: Any, ctx: Dict[str, Any]) -> None:
    """中心标记：穿过圆心的十字线，臂长 = R + gap。"""
    cx, cy = _p(ctx, "center", (0.0, 0.0))
    radius = float(_p(ctx, "radius", 10.0))
    gap = float(_p(ctx, "gap", 1.0))
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(cx, cy, 0.0), radius, label="AddCircle")
    arm = radius + gap
    add(ms, "AddLine", pt(cx - arm, cy), pt(cx + arm, cy), label="AddLine")
    add(ms, "AddLine", pt(cx, cy - arm), pt(cx, cy + arm), label="AddLine")


def build_balloon(doc: Any, ctx: Dict[str, Any]) -> None:
    """序号气泡：圆 + 引线 + 序号文字。

    本机实测：`AddMLeader` 能建出 AcDbMLeader，但**写不进 `TextString`**
    （赋值不报错、读回空串）。所以气泡用圆+线+文字拼，和别的符号一致。
    """
    x, y = _p(ctx, "tip", (0.0, 450.0))
    tx, ty = _p(ctx, "text", (30.0, 470.0))
    index = str(_p(ctx, "index", "1"))
    radius = float(_p(ctx, "radius", 4.0))
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(x, y, 0.0), radius, label="AddCircle")
    add(ms, "AddLine", pt(x + radius, y), pt(tx, ty), label="AddLine")
    add(ms, "AddText", index, pt(x - 1.2, y - 1.6), 3.5, label="AddText")
