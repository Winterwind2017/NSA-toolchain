"""文字类 builder：单行文字 / 多行文字 / 文字样式。"""

from __future__ import annotations

from typing import Any, Dict

from ..core import com
from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_text(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    add(ms, "AddText", str(_p(ctx, "text", "ACADKIT 文字")),
        pt(*_p(ctx, "insertion", (0.0, 200.0, 0.0))),
        float(_p(ctx, "height", 5.0)), label="AddText")


def build_mtext(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    add(ms, "AddMText", pt(*_p(ctx, "insertion", (0.0, 220.0, 0.0))),
        float(_p(ctx, "width", 80.0)), str(_p(ctx, "text", "多行文字 MTEXT")),
        label="AddMText")


def build_textstyle(doc: Any, ctx: Dict[str, Any]) -> None:
    name = str(_p(ctx, "name", "CN_STYLE"))
    style = com.retry(lambda: doc.TextStyles.Add(name), label="TextStyles.Add")
    style.SetFont(str(_p(ctx, "font", "SimSun")), False, False, 134, 2)
