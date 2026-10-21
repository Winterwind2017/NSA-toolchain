"""图框 / 标题栏 / 多布局。"""

from __future__ import annotations

from typing import Any, Dict

from ..core import com
from .helpers import add, dbl, ms_of, pt

TITLE_ATTRS = {"DWG_NO": "ACADKIT-001", "TITLE": "PART", "MATERIAL": "Q235",
               "SCALE": "1:1", "WEIGHT": "1.2", "DESIGNER": "AK"}


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_titleblock(doc: Any, ctx: Dict[str, Any]) -> None:
    """A3 图框（420×297）+ 标题栏块（6 个属性）插入到右下角。"""
    w = float(_p(ctx, "width", 420.0))
    h = float(_p(ctx, "height", 297.0))
    ms = ms_of(doc)
    pl = add(ms, "AddLightWeightPolyline", dbl([0, 0, w, 0, w, h, 0, h]),
             label="AddLightWeightPolyline")
    pl.Closed = True

    # 标题栏：180×56 的框（4 条线，刻意不用多段线：几何判据要按"新增 1 条闭合多段线"判）
    x0, y0, bw, bh = w - 180.0, 0.0, 180.0, 56.0
    for a, b in (((x0, y0), (x0 + bw, y0)), ((x0 + bw, y0), (x0 + bw, y0 + bh)),
                 ((x0 + bw, y0 + bh), (x0, y0 + bh)), ((x0, y0 + bh), (x0, y0))):
        add(ms, "AddLine", pt(*a), pt(*b), label="AddLine")

    blocks = com.retry(lambda: doc.Blocks, label="Blocks")
    try:
        blk = blocks.Item("TITLEBLOCK")
    except Exception:                               # noqa: BLE001
        blk = com.retry(lambda: blocks.Add(pt(0, 0, 0), "TITLEBLOCK"),
                        label="Blocks.Add")
        for i, tag in enumerate(TITLE_ATTRS):
            com.retry(lambda tag=tag, i=i: blk.AddAttribute(
                2.5, 0, tag, pt(2, 2 + i * 4, 0), tag, TITLE_ATTRS[tag]),
                 label="AddAttribute")
    ref = com.retry(lambda: ms.InsertBlock(pt(w - 178.0, 2.0, 0.0), "TITLEBLOCK",
                                           1.0, 1.0, 1.0, 0.0),
                    label="InsertBlock")
    for at in ref.GetAttributes():
        tag = str(at.TagString)
        if tag in TITLE_ATTRS:
            at.TextString = TITLE_ATTRS[tag]


def build_layout(doc: Any, ctx: Dict[str, Any]) -> None:
    """新建布局 + 一个视口；判据用"该布局视口数 +1"。"""
    name = str(_p(ctx, "name", "SHEET_A"))
    width = float(_p(ctx, "viewport_w", 200.0))
    height = float(_p(ctx, "viewport_h", 150.0))
    layouts = com.retry(lambda: doc.Layouts, label="Layouts")
    try:
        layout = layouts.Item(name)
        created = False
    except Exception:                               # noqa: BLE001
        layout = com.retry(lambda: layouts.Add(name), label="Layouts.Add")
        created = True
    doc.ActiveLayout = com.retry(lambda: layouts.Item(name), label="Layouts.Item")
    ps = com.retry(lambda: doc.PaperSpace, label="PaperSpace")
    before = _viewport_count(layout)
    com.retry(lambda: ps.AddPViewport(pt(width / 2 + 20, height / 2 + 20),
                                      width, height), label="AddPViewport")
    after = _viewport_count(layout)
    ctx.setdefault("artifacts", {})["layout"] = {
        "name": name, "created": created,
        "viewports_before": before, "viewports_after": after,
    }


def _viewport_count(layout: Any) -> int:
    try:
        blk = layout.Block
        return sum(1 for i in range(int(blk.Count))
                   if str(blk.Item(i).ObjectName) == "AcDbViewport")
    except Exception:                               # noqa: BLE001
        return -1
