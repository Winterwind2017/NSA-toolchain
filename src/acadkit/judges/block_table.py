"""块 + 属性 + 表格 / BOM 判据（JUDGE_SPEC 2.4 / 2.5）。

这两族必须**关联判**，只看计数会漏掉最典型的假成功：

* 块：`Blocks` 表 +1、`BlockReference` +1 都可能为真，但属性只写进去一半；
  L3 的判据是"属性个数 == 块定义里的 Attdef 数"（少一个就是假成功）；
* 表格：`AddTable` 返回对象、`SetText` 不报错，但落盘重开后单元格文字
  可能丢（本机实测：中文单元格重开后变成空串）。所以 L4 逐格比对。

本机实测（2026-10-21）：
* `IAcadBlock.AddAttribute(Height, Mode, Prompt, InsertionPoint, Tag, Value)`
  是本机唯一可用的属性定义入口；
* `InsertBlock(...).GetAttributes()` 返回 tuple，`TextString` 可直接写；
* 块属性重开后保持（中文也保住了）；
* 表格中文单元格 `SetText` → 内存读回正确，但**重开后丢失**（Standard 文字
  样式不支持中文）。判据必须能抓到这个，所以这里逐格比。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import (Entity, Readback, new_entities, num, pt_close,
                   reopen_check, verdict)
from .read import attdefs_by_tag, attrs_by_tag


def _new_one(rb: Readback, type_name: str) -> Optional[Entity]:
    new = new_entities(rb, type_name)
    return new[0] if len(new) == 1 else None


# ── 块定义 ──────────────────────────────────────────────────────────
def judge_block_define(rb: Readback, *, block_name: str,
                       attdefs: Dict[str, str],
                       entity_types: Optional[Dict[str, int]] = None
                       ) -> Dict[str, Any]:
    before = rb.before.meta.get("blocks") or {}
    memory = rb.memory.meta.get("blocks") or {}
    row = memory.get(block_name)
    re = rb.reopened.meta.get("blocks") if rb.reopened else None
    re_row = (re or {}).get(block_name)
    got_attdefs = attdefs_by_tag(row) if row else {}
    expected_types = entity_types or {"CIRCLE": 1, "ATTRIBUTEDEFINITION": len(attdefs)}

    checks = {
        "new_block": bool(row is not None and block_name not in before),
        "entity_count": bool(row is not None
                             and (row.get("types") or {}) == expected_types),
        "attdef_count": bool(row is not None
                             and len(row.get("attdefs") or []) == len(attdefs)),
        "attdef_values": got_attdefs == {k: str(v) for k, v in attdefs.items()},
        "reopen": bool(re_row is not None
                       and attdefs_by_tag(re_row) == got_attdefs
                       and (re_row.get("types") or {}) == (row.get("types") or {})),
    }
    detail = {
        "block_name": block_name,
        "block_entity_count": row.get("count") if row else None,
        "block_types": row.get("types") if row else None,
        "block_types_expected": expected_types,
        "attdefs_read": got_attdefs,
        "attdefs_expected": {k: str(v) for k, v in attdefs.items()},
        "attdef_count": len(row.get("attdefs") or []) if row else 0,
        "reopened_block_present": re_row is not None,
        "blocks_before": len(before),
        "blocks_memory": len(memory),
    }
    raw = {"block": row, "all_blocks": sorted(memory)}
    return verdict(checks, detail, raw)


# ── 块插入 + 属性值 ─────────────────────────────────────────────────
def judge_block_insert(rb: Readback, *, block_name: str,
                       attrs: Dict[str, str],
                       insertion: Optional[tuple] = None) -> Dict[str, Any]:
    new = new_entities(rb, "BLOCKREFERENCE")
    ent = new[0] if len(new) == 1 else None
    got = attrs_by_tag(ent.attrs) if ent else {}
    expected = {k: str(v) for k, v in attrs.items()}
    re_ok, re_detail = (reopen_check(rb, ent, ())
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新块引用"}}))
    if re_ok:
        hit = rb.reopened.by_handle(ent.handle) if rb.reopened else None
        re_got = attrs_by_tag(hit.attrs) if hit else {}
        re_ok = re_got == got
        if not re_ok:
            re_detail.setdefault("mismatch", {})["attributes"] = [got, re_got]
    checks = {
        "count": len(new) == 1 and rb.memory.count("BLOCKREFERENCE") == \
                 rb.before.count("BLOCKREFERENCE") + 1,
        "type": bool(ent) and ent.get("ObjectName") == "AcDbBlockReference",
        "name": bool(ent) and str(ent.get("Name")) == block_name,
        "insertion": (pt_close(ent.get("InsertionPoint"), insertion)
                      if (ent and insertion) else bool(ent)),
        "attr_count": len(got) == len(expected),
        "attr_values": got == expected,
        "reopen": re_ok,
    }
    detail = {
        "handle": ent.handle if ent else None,
        "block_name": block_name,
        "block_name_read": ent.get("Name") if ent else None,
        "insertion_du": ent.get("InsertionPoint") if ent else None,
        "insertion_expected_du": list(insertion) if insertion else None,
        "attributes_read": got,
        "attributes_expected": expected,
        "attr_count": len(got),
        "attr_count_expected": len(expected),
        "reopen": re_detail,
    }
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "ref": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


# ── 表格 / BOM ──────────────────────────────────────────────────────
def judge_table(rb: Readback, *, rows: int, cols: int,
                cells: Dict[str, str],
                sum_column: Optional[int] = None,
                detail_rows: Optional[Any] = None,
                total_row: Optional[int] = None) -> Dict[str, Any]:
    """`cells` 的键是 "r,c" 字符串（字典要可 JSON 化）。

    `sum_column`：给了就做 L3 —— 合计行该列 == 明细行之和。
    行区间默认按"表头在 0 行、合计在最后一行"取；BOM 这类带标题行的表要显式
    传 `detail_rows=(2,3), total_row=4`（本机实测：ACDBTABLE 的第 0 行是**合并
    的标题行**，往它的第 1..n 列写的东西落盘重开后会丢）。
    """
    ent = _new_one(rb, "ACDBTABLE")
    grid = (ent.get("cells") if ent else None) or []
    got_rows = ent.get("rows") if ent else None
    got_cols = ent.get("columns") if ent else None

    def cell(r: int, c: int) -> Optional[str]:
        try:
            return grid[r][c]
        except (IndexError, TypeError):
            return None

    mismatched = {}
    for key, want in cells.items():
        r, c = (int(x) for x in key.split(","))
        got = cell(r, c)
        if (got or "").strip() != str(want).strip():
            mismatched[key] = [want, got]

    sum_ok = None
    sum_detail: Dict[str, Any] = {}
    if sum_column is not None:
        try:
            total_row = rows - 1 if total_row is None else int(total_row)
            drows = (list(range(1, rows - 1)) if detail_rows is None
                     else list(detail_rows))
            total = num(cell(total_row, sum_column))
            parts = [num(cell(r, sum_column)) for r in drows]
            sum_detail = {"total_row": total_row, "detail_rows": drows,
                          "total_read": total, "parts_read": parts,
                          "sum_parts": (round(sum(p for p in parts), 6)
                                        if all(p is not None for p in parts) else None)}
            sum_ok = bool(total is not None and all(p is not None for p in parts)
                          and abs(total - sum(p for p in parts)) <= 1e-9)
        except Exception as exc:                        # noqa: BLE001
            sum_detail = {"error": "%s: %s" % (type(exc).__name__, exc)}
            sum_ok = False

    re_ok, re_detail = (reopen_check(rb, ent, ("rows", "columns"))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新表格"}}))
    if re_ok:
        hit = rb.reopened.by_handle(ent.handle) if rb.reopened else None
        re_grid = (hit.get("cells") if hit else None) or []
        re_ok = re_grid == grid
        if not re_ok:
            re_detail.setdefault("mismatch", {})["cells"] = [grid, re_grid]

    checks = {
        "count": len(new_entities(rb, "ACDBTABLE")) == 1
                 and rb.memory.count("ACDBTABLE") == rb.before.count("ACDBTABLE") + 1,
        "type": bool(ent) and ent.get("ObjectName") == "AcDbTable",
        "size": bool(ent) and got_rows == rows and got_cols == cols,
        "cells": bool(ent) and not mismatched,
        "reopen": re_ok,
    }
    if sum_column is not None:
        checks["sum"] = bool(sum_ok)
    detail = {
        "handle": ent.handle if ent else None,
        "rows": got_rows,
        "rows_expected": rows,
        "columns": got_cols,
        "columns_expected": cols,
        "grid": grid,
        "cells_expected": cells,
        "cell_mismatch": mismatched,
        "sum_column": sum_column,
        "sum": sum_detail,
        "reopen": re_detail,
    }
    raw = {"before_counts": rb.before.counts, "memory_counts": rb.memory.counts,
           "table": ent.attrs if ent else None}
    return verdict(checks, detail, raw)
