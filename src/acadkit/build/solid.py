"""3D 实体：基本体 / 拉伸（体积判据）。

体积用 `IAcad3DSolid.Volume` 读回（本机实测可用：40×20×10 box → 8000.0，
r10×h20 圆柱 → 6283.185，拉伸 40×30×10 → 12000.0）。

**旋转**（`AddRevolvedSolid`）本机不可用：XY 矩形、圆、3D 多段线三种轮廓
都报"输入无效"，命令行 `_.REVOLVE` 也没生成实体 —— 见 `docs/UNSUPPORTED.md`。
"""

from __future__ import annotations

from typing import Any, Dict

from .helpers import add, add_solid, ms_of, region_from_polyline

BOX = (40.0, 20.0, 10.0)


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_primitives(doc: Any, ctx: Dict[str, Any]) -> None:
    """三个基本体：盒子 / 圆柱 / 球。体积解析值由判据对照。"""
    add_solid(doc, "box", origin=(0.0, 0.0, 0.0), l=BOX[0], w=BOX[1], h=BOX[2])
    add_solid(doc, "cylinder", center=(100.0, 0.0, 0.0), r=10.0, h=20.0)
    add_solid(doc, "sphere", center=(200.0, 0.0, 0.0), r=10.0)


def build_extrude(doc: Any, ctx: Dict[str, Any]) -> None:
    """闭合轮廓（40×30）拉伸 10mm → 体积 12000（解析值）。"""
    ms = ms_of(doc)
    reg = region_from_polyline(ms, [(0, 0), (40, 0), (40, 30), (0, 30)])
    add(ms, "AddExtrudedSolid", reg, 10.0, 0.0, label="AddExtrudedSolid")
