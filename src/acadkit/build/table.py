"""表格 builder：通用网格（BOM 见 block_table.py）。"""

from __future__ import annotations

from typing import Any, Dict

from ..core import com
from .helpers import add, ms_of, pt


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


GRID_CELLS = {
    "0,0": "NO.", "0,1": "NAME", "0,2": "QTY",
    "1,0": "1", "1,1": "BRACKET", "1,2": "2",
    "2,0": "2", "2,1": "PLATE", "2,2": "3",
    "3,0": "TOTAL", "3,2": "5",
}

CN_CELLS = {
    "0,0": "明细表",
    "1,0": "序号", "1,1": "名称",
    "2,0": "1", "2,1": "支座",
}

CN_STYLE = "CN"


def build_cn_table(doc: Any, ctx: Dict[str, Any]) -> None:
    """中文表格：先建 TrueType（SimSun）样式，再逐格 SetCellTextStyle + SetText。

    本机实测（2026-10-21，RE 出的 API）：`AcadTable.SetCellTextStyle(row, col, 样式名)`
    确实存在；不设样式时默认 `Standard`（txt.shx）没有 CJK 字形，中文单元格
    落盘重开会丢字。设了 CN 样式后重开中文完好。
    """
    name = str(_p(ctx, "style", CN_STYLE))
    cells = _p(ctx, "cells", None) or CN_CELLS
    rows = int(_p(ctx, "rows", 3))
    cols = int(_p(ctx, "cols", 2))
    styles = com.retry(lambda: doc.TextStyles, label="TextStyles")
    try:
        style = styles.Item(name)
    except Exception:                               # noqa: BLE001
        style = com.retry(lambda: styles.Add(name), label="TextStyles.Add")
        try:
            style.SetFont(str(_p(ctx, "font", "SimSun")), False, False, 134, 2)
        except Exception as exc:                    # noqa: BLE001
            ctx["notes"].append("SetFont 失败：%s: %s" % (type(exc).__name__, exc))
    ms = ms_of(doc)
    table = add(ms, "AddTable", pt(*_p(ctx, "insertion", (0.0, -200.0, 0.0))),
                rows, cols, float(_p(ctx, "row_height", 8.0)),
                float(_p(ctx, "col_width", 40.0)), label="AddTable")
    for key, val in cells.items():
        r, c = (int(x) for x in key.split(","))
        try:
            table.SetCellTextStyle(r, c, name)
        except Exception as exc:                    # noqa: BLE001
            ctx["notes"].append("SetCellTextStyle(%d,%d) 失败：%s: %s"
                                % (r, c, type(exc).__name__, exc))
        table.SetText(r, c, str(val))
    ctx.setdefault("artifacts", {})["cn_table"] = {
        "style": name, "rows": rows, "cols": cols, "cells": cells,
    }


def build_grid_table(doc: Any, ctx: Dict[str, Any]) -> None:
    """4×3 通用网格：第 0 行不是标题行时会被合并，所以这里按 5 行排（标题+表头+2 明细+合计）。

    本机实测：ACDBTABLE 第 0 行是**合并标题行**，往它的第 1..n 列 SetText，
    内存读得到、落盘重开变空串。所以表头放第 1 行。
    """
    cells = _p(ctx, "cells", None) or {
        "0,0": "GRID",
        "1,0": "NO.", "1,1": "NAME", "1,2": "QTY",
        "2,0": "1", "2,1": "BRACKET", "2,2": "2",
        "3,0": "2", "3,1": "PLATE", "3,2": "3",
        "4,0": "TOTAL", "4,2": "5",
    }
    rows = int(_p(ctx, "rows", 5))
    cols = int(_p(ctx, "cols", 3))
    ms = ms_of(doc)
    table = add(ms, "AddTable", pt(*_p(ctx, "insertion", (0.0, -120.0, 0.0))),
                rows, cols, float(_p(ctx, "row_height", 8.0)),
                float(_p(ctx, "col_width", 40.0)), label="AddTable")
    for key, val in cells.items():
        r, c = (int(x) for x in key.split(","))
        table.SetText(r, c, str(val))
