"""视图 / 缩放。"""

from __future__ import annotations

from typing import Any, Dict

from ..core import com
from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_zoom_extents(doc: Any, ctx: Dict[str, Any]) -> None:
    """画一个圆 → ZoomExtents → 视图必须把整张图包进去。"""
    cx, cy = _p(ctx, "center", (500.0, 500.0))
    radius = float(_p(ctx, "radius", 100.0))
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(cx, cy, 0.0), radius, label="AddCircle")
    app = com.retry(lambda: doc.Application, label="Application")
    app.ZoomExtents()
    ctx.setdefault("artifacts", {})["zoom"] = {
        "center": [cx, cy], "radius": radius}
