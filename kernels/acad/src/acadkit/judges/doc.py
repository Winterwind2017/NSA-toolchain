"""文档类判据：新建图纸 / 关闭图纸。

这两条**不判几何**——它们判的是"文档生命周期"：

L1  文档数：新建后 +1、关闭后回到原位（`env_documents` 之外再单独判一次，
    这样失败时能指出是"没建出来"还是"没关掉"）
L2  属性读回：新文档 `Name` 非空、`ModelSpace.Count` 为 0（真是一张空图）
L3  行为自洽：`ActiveDocument` 在 Add 后指向新文档、关掉后回到用例文档
L4  无模态：关文档耗时 ≤ `CLOSE_LIMIT_S`（弹了"是否保存"会明显超时）

判据只读 builder 记下的 `ctx["artifacts"]`，不重新调 COM：这样"读到什么"
和"做了什么"是同一份事实，不会出现"判据自己又去开一张图"。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import Readback, verdict

CLOSE_LIMIT_S = 5.0


def _rec(ctx: Dict[str, Any], key: str) -> Dict[str, Any]:
    return dict((ctx.get("artifacts") or {}).get(key) or {})


def _num(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def judge_new_drawing(rb: Readback, ctx: Dict[str, Any]) -> Dict[str, Any]:
    rec = _rec(ctx, "doc_new")
    before = _num(rec.get("count_before"))
    after_add = _num(rec.get("count_after_add"))
    final = _num(rec.get("count_final"))
    name = str(rec.get("name") or "")
    case_doc = str(rec.get("case_doc") or "")
    entities = _num(rec.get("entities"))
    elapsed = rec.get("close_elapsed_s")
    active_after_add = str(rec.get("active_after_add") or "")
    active_final = str(rec.get("active_final") or "")

    opened = (before is not None and after_add is not None and after_add == before + 1)
    closed = (before is not None and final is not None and final == before)
    named = bool(name) and name != case_doc
    empty = entities == 0
    became_active = bool(name) and active_after_add == name
    restored = (not case_doc) or active_final == case_doc
    fast = elapsed is not None and float(elapsed) <= CLOSE_LIMIT_S

    checks = {
        "count_added": bool(opened),
        "count_restored": bool(closed),
        "new_name": bool(named),
        "empty_modelspace": bool(empty),
        "became_active": bool(became_active),
        "active_restored": bool(restored),
        "close_fast": bool(fast),
    }
    detail = {
        "counts": {"before": before, "after_add": after_add, "final": final},
        "name": name,
        "case_doc": case_doc,
        "entities": entities,
        "active_after_add": active_after_add,
        "active_final": active_final,
        "close_elapsed_s": elapsed,
        "close_limit_s": CLOSE_LIMIT_S,
    }
    return verdict(checks, detail, {"artifact": "doc_new"})


def judge_close_drawing(rb: Readback, ctx: Dict[str, Any]) -> Dict[str, Any]:
    rec = _rec(ctx, "doc_close")
    before = _num(rec.get("count_before"))
    after_add = _num(rec.get("count_after_add"))
    final = _num(rec.get("count_final"))
    name = str(rec.get("name") or "")
    case_doc = str(rec.get("case_doc") or "")
    elapsed = rec.get("close_elapsed_s")
    active_final = str(rec.get("active_final") or "")

    opened = (before is not None and after_add is not None and after_add == before + 1)
    closed = (before is not None and final is not None and final == before)
    named = bool(name)
    restored = (not case_doc) or active_final == case_doc
    fast = elapsed is not None and float(elapsed) <= CLOSE_LIMIT_S
    # 关掉的不能是用例自己的文档（用例文档得留着给 L4 存盘重开用）
    not_case_doc = bool(name) and name != case_doc

    checks = {
        "scratch_opened": bool(opened),
        "scratch_closed": bool(closed),
        "scratch_named": bool(named),
        "scratch_not_case_doc": bool(not_case_doc),
        "active_restored": bool(restored),
        "close_fast": bool(fast),
    }
    detail = {
        "counts": {"before": before, "after_add": after_add, "final": final},
        "name": name,
        "case_doc": case_doc,
        "active_final": active_final,
        "close_elapsed_s": elapsed,
        "close_limit_s": CLOSE_LIMIT_S,
    }
    return verdict(checks, detail, {"artifact": "doc_close"})
