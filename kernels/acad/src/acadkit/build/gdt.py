"""形位公差（GD&T）：ACDBFCF 实体。"""

from __future__ import annotations

from typing import Any, Dict

from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_gdt(doc: Any, ctx: Dict[str, Any]) -> None:
    """`\\Fgdt;n` = 垂直度符号；`%%v` = 框分隔。本机实测实体类型 = AcDbFcf。"""
    text = str(_p(ctx, "text", "{\\Fgdt;n}%%v0.02"))
    pos = _p(ctx, "insertion", (0.0, 300.0, 0.0))
    direction = _p(ctx, "direction", (1.0, 0.0, 0.0))
    ms = ms_of(doc)
    add(ms, "AddTolerance", text, pt(*pos), pt(*direction), label="AddTolerance")
