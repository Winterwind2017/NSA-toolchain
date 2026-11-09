"""块 / 属性 / 表格 builder。"""

from __future__ import annotations

from typing import Any, Dict

from ..core import com
from .helpers import define_block, insert_block, ms_of, pt

# BOM 表内容：第 0 行是合并标题行（本机实测：往它的第 1..n 列 SetText，
# 内存读得到但落盘重开变空），所以表头放第 1 行。
BOM_CELLS = {"0,0": "BOM",
             "1,0": "NO.", "1,1": "NAME", "1,2": "QTY",
             "2,0": "1", "2,1": "BRACKET", "2,2": "2",
             "3,0": "2", "3,1": "PLATE", "3,2": "3",
             "4,0": "TOTAL", "4,2": "5"}


def build_block_define(doc: Any, ctx: Dict[str, Any]) -> None:
    define_block(doc)


def build_block_insert(doc: Any, ctx: Dict[str, Any]) -> None:
    define_block(doc)
    insert_block(doc, {"PART_NO": "P-777", "MATERIAL": "45#"})


def build_block_short(doc: Any, ctx: Dict[str, Any]) -> None:
    """负例：插入后删掉一个属性，属性个数应当判不过。"""
    define_block(doc)
    ref = insert_block(doc, {"PART_NO": "P-777"})
    removed = None
    for at in ref.GetAttributes():
        if str(at.TagString) == "MATERIAL":
            try:
                at.Delete()
                removed = "MATERIAL"
            except Exception as exc:                # noqa: BLE001
                ctx["notes"].append("删属性失败：%s: %s" % (type(exc).__name__, exc))
    ctx["artifacts"]["removed"] = removed
    if removed is None:
        ctx["notes"].append("没能删掉属性——负例退化为'值不对'")


def build_table(doc: Any, ctx: Dict[str, Any]) -> None:
    ms = ms_of(doc)
    tbl = com.retry(lambda: ms.AddTable(pt(0, -60, 0), 5, 3, 8.0, 40.0),
                    label="AddTable")
    for key, v in BOM_CELLS.items():
        r, c = (int(x) for x in key.split(","))
        try:
            tbl.SetText(r, c, v)
        except Exception as exc:                    # noqa: BLE001
            ctx["notes"].append("SetText(%s,%s) 失败：%s" % (r, c, exc))
    ctx["artifacts"]["table"] = tbl
