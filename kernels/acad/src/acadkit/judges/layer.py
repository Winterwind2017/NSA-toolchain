"""图层状态判据（保存 → 删层 → 恢复）。"""

from __future__ import annotations

from typing import Any, Dict

from .base import Readback, close, value_same, verdict


def judge_layer_current(rb: Readback, *, name: str) -> Dict[str, Any]:
    """设当前层：ActiveLayer 读回 + 新建实体确实落在该层。"""
    tables = rb.memory.meta.get("tables") or {}
    re_tables = ((rb.reopened.meta.get("tables") or {})
                 if rb.reopened else {})
    new_circles = [e for e in rb.memory.of_type("CIRCLE")
                   if e.handle not in rb.before.handles]
    ent = new_circles[0] if len(new_circles) == 1 else None
    checks = {
        "layer_row": name in (tables.get("layers") or {}),
        "active_layer": tables.get("active_layer") == name,
        "entity_on_layer": bool(ent is not None and ent.get("Layer") == name),
        "reopen": bool(re_tables.get("active_layer") == name
                       and (re_tables.get("layers") or {}).get(name) is not None),
    }
    detail = {"name": name,
              "active_layer_read": tables.get("active_layer"),
              "entity_layer": ent.get("Layer") if ent else None,
              "active_reopened": re_tables.get("active_layer")}
    return verdict(checks, detail, {"tables": tables})


def judge_layer_snapshot(rb: Readback, *, recorded: Dict[str, Any]) -> Dict[str, Any]:
    """属性级图层状态：改动确实发生、恢复后逐属性一致（内存 + 重开）。"""
    snap = recorded.get("snapshot") or {}
    changed = recorded.get("changed") or {}
    mutated = recorded.get("mutated") or {}
    tables = rb.memory.meta.get("tables") or {}
    rows = tables.get("layers") or {}
    re_rows = ((rb.reopened.meta.get("tables") or {}).get("layers") or {}
               if rb.reopened else {})
    checks: Dict[str, bool] = {}
    for lname, props in mutated.items():
        for key, want in props.items():
            checks["mutated:%s.%s" % (lname, key)] = value_same(
                (changed.get(lname) or {}).get(key), want)
            checks["restored:%s.%s" % (lname, key)] = value_same(
                (rows.get(lname) or {}).get(key), (snap.get(lname) or {}).get(key))
            checks["reopen:%s.%s" % (lname, key)] = value_same(
                (re_rows.get(lname) or {}).get(key), (snap.get(lname) or {}).get(key))
    # 没被改的属性也必须原样（只挑快照里有、读回也有的键）
    for lname, props in snap.items():
        row = rows.get(lname) or {}
        for key, want in props.items():
            if key in row and lname in mutated:
                pass
            if key in row:
                checks.setdefault("restored:%s.%s" % (lname, key),
                                  value_same(row.get(key), want))
    detail = {"snapshot_layers": len(snap), "mutated": mutated,
              "changed": {k: changed.get(k) for k in mutated},
              "restored": {k: rows.get(k) for k in mutated},
              "reopened": {k: re_rows.get(k) for k in mutated}}
    return verdict(checks, detail, {"recorded": recorded.get("mutated")})


def judge_layer_state(rb: Readback, *, name: str, color: int,
                      recorded: Dict[str, Any]) -> Dict[str, Any]:
    tables = (rb.memory.meta.get("tables") or {})
    row = (tables.get("layers") or {}).get(name)
    re_tables = ((rb.reopened.meta.get("tables") or {})
                 if rb.reopened else {})
    re_row = (re_tables.get("layers") or {}).get(name)
    checks = {
        "deleted": bool(recorded.get("deleted")),
        "count_dropped": (recorded.get("count_after_delete")
                          == recorded.get("count_before", 0) - 1),
        "count_restored": (recorded.get("count_after_restore")
                           == recorded.get("count_before")),
        "layer_back": row is not None,
        "color_restored": bool(row is not None and close(row.get("Color"), color)),
        "reopen": bool(re_row is not None
                       and close(re_row.get("Color"), color)),
    }
    detail = {"name": name, "color_expected": color,
              "row": row, "row_reopened": re_row,
              "counts": {k: recorded.get(k) for k in
                         ("count_before", "count_after_delete",
                          "count_after_restore")},
              "state_name": recorded.get("state")}
    return verdict(checks, detail, {"row": row, "recorded": recorded})
