"""通用判据：一条"新建了某个实体，并且它的属性读回来对"的判据。

`docs/JUDGE_SPEC.md` 要求每个能力都有 L1–L4，但一大半能力是同一个形状：

    动作：往模型空间/命名表里加东西
    证明：类型对 + 关键属性读回对 + 存盘重开后仍然对

所以这里把这条形状抽成三个通用判据，族模块只在需要特殊几何（体积、三视图、
表格合计）时才另写：

* :func:`judge_new_entity` —— 新增一个实体（按类型），逐属性比对；
* :func:`judge_delta`      —— 一次动作让**多种**实体计数按预期变化（符号类）；
* :func:`judge_named_table` —— 命名表（图层/文字样式/标注样式/布局）新增/改行。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .base import (Entity, Readback, new_entities, num, rel_close,
                   reopen_check, value_same, verdict)


def _same(want: Any, got: Any, tol: float) -> bool:
    if want is None:
        return got is None
    return value_same(want, got, tol)


def judge_new_entity(rb: Readback, *, type_name: str, object_name: Optional[str] = None,
                     expected: Optional[Dict[str, Any]] = None,
                     contains: Optional[Dict[str, str]] = None,
                     count_delta: int = 1, tol: float = 1e-6,
                     extra: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    new = new_entities(rb, type_name)
    ent: Optional[Entity] = new[0] if len(new) == 1 else None
    checks: Dict[str, bool] = {
        "count": (rb.memory.count(type_name) == rb.before.count(type_name) + count_delta
                  and len(new) == count_delta),
        "type": bool(ent) and (object_name is None
                               or ent.get("ObjectName") == object_name),
    }
    detail: Dict[str, Any] = {"handle": ent.handle if ent else None,
                              "type": type_name,
                              "object_name": ent.get("ObjectName") if ent else None,
                              "attributes": {}}
    for key, want in (expected or {}).items():
        got = ent.get(key) if ent else None
        checks["attr:" + key] = _same(want, got, tol)
        detail["attributes"][key] = {"expected": want, "read": got}
    for key, needle in (contains or {}).items():
        got = str(ent.get(key)) if ent else ""
        checks["contains:" + key] = needle in got
        detail["attributes"].setdefault(key, {})["contains"] = needle
        detail["attributes"][key]["read"] = got

    re_ok, re_detail = (reopen_check(rb, ent, tuple((expected or {}).keys()))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新实体"}}))
    if re_ok:
        re_ok = (rb.reopened is not None
                 and rb.reopened.counts == rb.memory.counts)
    checks["reopen"] = bool(re_ok)
    detail["reopen"] = re_detail
    detail["counts_before"] = rb.before.counts
    detail["counts_memory"] = rb.memory.counts
    for key, val in (extra or {}).items():
        checks["extra:" + key] = bool(val)
    raw = {"before": rb.before.counts, "memory": rb.memory.counts,
           "entity": ent.attrs if ent else None}
    return verdict(checks, detail, raw)


def judge_delta(rb: Readback, *, expect: Dict[str, int],
                tol: float = 1e-6,
                attrs: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """一次动作让多个类型的计数按 `expect` 变化（符号类：几条线+几个文字）。

    `attrs` 可选：对新增实体逐条做属性比对（按谓词）。
    """
    checks: Dict[str, bool] = {}
    detail: Dict[str, Any] = {"deltas": {}, "expected": expect}
    for type_name, delta in expect.items():
        before = rb.before.count(type_name)
        memory = rb.memory.count(type_name)
        ok = (memory == before + delta)
        checks["count:" + type_name] = ok
        detail["deltas"][type_name] = {"before": before, "memory": memory,
                                       "expected": delta}
    for i, spec in enumerate(attrs or []):
        type_name = spec["type"]
        got = rb.memory.of_type(type_name)
        # 取最后新增的那个（builder 已知顺序；按句柄差集更稳）
        new = [e for e in got if e.handle not in rb.before.handles]
        target = new[-1] if new else None
        for key, want in (spec.get("expected") or {}).items():
            checks["attr:%d:%s" % (i, key)] = bool(
                target and _same(want, target.get(key), tol))
            detail.setdefault("attrs", []).append(
                {"type": type_name, "key": key, "expected": want,
                 "read": target.get(key) if target else None})
    re_ok = bool(rb.reopened is not None
                 and rb.reopened.counts == rb.memory.counts)
    checks["reopen"] = re_ok
    return verdict(checks, detail, {"before": rb.before.counts,
                                    "memory": rb.memory.counts})


def judge_named_table(rb: Readback, *, table: str, name: str,
                      expected: Optional[Dict[str, Any]] = None,
                      contains: Optional[Dict[str, str]] = None,
                      expect_new: bool = True,
                      tol: float = 1e-6) -> Dict[str, Any]:
    """命名表判据（图层 / 文字样式 / 标注样式 / 布局）。"""
    before = (rb.before.meta.get("tables") or {}).get(table) or {}
    memory = (rb.memory.meta.get("tables") or {}).get(table) or {}
    reopened = ((rb.reopened.meta.get("tables") or {}).get(table)
                if rb.reopened else None)
    row = memory.get(name)
    checks: Dict[str, bool] = {
        "new_row": bool(row is not None and (name not in before or not expect_new)),
        "row_exists": bool(row is not None),
    }
    detail: Dict[str, Any] = {"table": table, "name": name, "row": row,
                              "rows_before": len(before), "rows_memory": len(memory)}
    for key, want in (expected or {}).items():
        got = (row or {}).get(key)
        checks["attr:" + key] = _same(want, got, tol)
        detail.setdefault("attributes", {})[key] = {"expected": want, "read": got}
    for key, needle in (contains or {}).items():
        got = str((row or {}).get(key))
        checks["contains:" + key] = needle in got
        detail.setdefault("attributes", {})[key] = {"contains": needle, "read": got}
    checks["reopen"] = bool(reopened is not None and name in reopened
                            and _row_same(reopened.get(name), row, expected or {}))
    if reopened is not None:
        detail["row_reopened"] = reopened.get(name)
    return verdict(checks, detail, {"row": row})


def _row_same(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]],
              keys: Dict[str, Any], tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return False
    for key in keys:
        if not _same(b.get(key), a.get(key), tol):
            return False
    return True


def judge_volume(rb: Readback, *, expected: float, rel: float = 0.01,
                 type_name: str = "3DSOLID") -> Dict[str, Any]:
    """3D 实体/面域的体积判据（`docs/JUDGE_SPEC.md` 2.6 的 L3）。"""
    ent: Optional[Entity] = new_entities(rb, type_name)[0] \
        if len(new_entities(rb, type_name)) == 1 else None
    vol = num(ent.get("Volume")) if ent else None
    checks = {
        "count": bool(ent),
        "type": bool(ent) and ent.get("ObjectName") in ("AcDb3dSolid", "AcDbRegion"),
        "volume": rel_close(vol, expected, rel),
    }
    re_ok, re_detail = (reopen_check(rb, ent, ("Volume",))
                        if ent else (False, {"mismatch": {"entity": "没有唯一定位到新实体"}}))
    checks["reopen"] = bool(re_ok)
    detail = {"handle": ent.handle if ent else None,
              "volume_expected": round(expected, 6),
              "volume_read": vol,
              "rel_tol": rel,
              "reopen": re_detail}
    return verdict(checks, detail, {"entity": ent.attrs if ent else None})
