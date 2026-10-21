"""布尔运算 / 剖切。

本机实测（2026-10-21）：ActiveX `Solid3D.Boolean` 不可靠 —— union(1) 算出
4000（应为 12000），`Boolean(3, …)` 直接报"参数 Operation 无效"；而命令行
`_.UNION` 得到 12000。所以这里走命令行 + **按句柄精确选择**。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .helpers import add_solid, boolean, send

BOX = (40.0, 20.0, 10.0)
TOOL = (20.0, 20.0, 10.0)
OFFSET = 20.0
# ★ 本机实测：AddBox 的 origin 是**中心**不是角点（由并集体积反推）。
# 体积：A=8000、B=4000、重叠 10×20×10=2000
#   union = 10000 / subtract = 6000 / intersect = 2000（三个都不同，判据能区分）


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def _two_boxes(doc: Any) -> List[Any]:
    a = add_solid(doc, "box", origin=(0.0, 0.0, 0.0), l=BOX[0], w=BOX[1], h=BOX[2])
    b = add_solid(doc, "box", origin=(OFFSET, 0.0, 0.0), l=TOOL[0], w=TOOL[1],
                  h=TOOL[2])
    return [a, b]


def _run(doc: Any, ctx: Dict[str, Any], op: str) -> None:
    ents = _two_boxes(doc)
    info = boolean(doc, op, ents)
    ctx.setdefault("artifacts", {})["boolean"] = info


def build_union(doc: Any, ctx: Dict[str, Any]) -> None:
    _run(doc, ctx, "union")


def build_subtract(doc: Any, ctx: Dict[str, Any]) -> None:
    _run(doc, ctx, "subtract")


def build_intersect(doc: Any, ctx: Dict[str, Any]) -> None:
    _run(doc, ctx, "intersect")


def build_slice(doc: Any, ctx: Dict[str, Any]) -> None:
    """SLICE：用平面把盒子切成两半，保留两侧（体积之和 = 原体积）。"""
    box = add_solid(doc, "box", origin=(0.0, 0.0, 0.0), l=BOX[0], w=BOX[1], h=BOX[2])
    handle = str(box.Handle)
    lisp = ('(vl-cmdf "_.SLICE" (handent "%s") "" '
            '"_3points" (list 0.0 0.0 0.0) (list 0.0 10.0 0.0) '
            '(list 0.0 0.0 10.0) "_Both")' % handle)
    send(doc, lisp, settle=1.0)
    ctx.setdefault("artifacts", {})["slice"] = {"handle": handle}

