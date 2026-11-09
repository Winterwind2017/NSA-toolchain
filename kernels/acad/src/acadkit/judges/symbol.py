"""符号类判据（粗糙度 / 焊接 / 中心线 / 中心标记 / 气泡）。

这些都是"用基本图元拼的符号"，所以判据看**图元计数 + 文字内容 + 关键几何**。
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import generic as gd
from .base import Readback, num, pt3, verdict


def judge_roughness(rb: Readback, *, text: str = "Ra 3.2") -> Dict[str, Any]:
    return gd.judge_delta(rb, expect={"LINE": 3, "TEXT": 1},
                          attrs=[{"type": "TEXT",
                                  "expected": {"TextString": text}}])


def judge_weld(rb: Readback, *, text: str = "6") -> Dict[str, Any]:
    return gd.judge_delta(rb, expect={"LINE": 2, "TEXT": 1},
                          attrs=[{"type": "TEXT",
                                  "expected": {"TextString": text}}])


def judge_centerline(rb: Readback, *, length: float,
                     linetype: str) -> Dict[str, Any]:
    return gd.judge_new_entity(rb, type_name="LINE", object_name="AcDbLine",
                               expected={"Length": length, "Linetype": linetype})


def judge_centermark(rb: Readback, *, center, arm: float) -> Dict[str, Any]:
    c = pt3(center)
    new = [e for e in rb.memory.of_type("LINE")
           if e.handle not in rb.before.handles]
    ok_mid = True
    rows: List[Dict[str, Any]] = []
    for e in new:
        p1, p2 = pt3(e.get("StartPoint")), pt3(e.get("EndPoint"))
        if p1 is None or p2 is None or c is None:
            ok_mid = False
            continue
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        same = abs(mid[0] - c[0]) <= 1e-6 and abs(mid[1] - c[1]) <= 1e-6
        length = num(e.get("Length"))
        ok_mid = ok_mid and same
        rows.append({"mid": mid, "length": length,
                     "through_center": same,
                     "length_ok": bool(length is not None
                                       and abs(length - 2 * arm) <= 1e-6)})
    checks = {
        "two_lines": len(new) == 2,
        "through_center": ok_mid,
        "arm_length": all(r.get("length_ok") for r in rows) and len(rows) == 2,
        "reopen": bool(rb.reopened is not None
                       and rb.reopened.count("LINE") == rb.memory.count("LINE")),
    }
    detail = {"center": list(c) if c else None, "arm_expected": arm, "lines": rows}
    return verdict(checks, detail, {"lines": [e.attrs for e in new]})


def judge_balloon(rb: Readback, *, index: str = "1") -> Dict[str, Any]:
    return gd.judge_delta(rb, expect={"CIRCLE": 1, "LINE": 1, "TEXT": 1},
                          attrs=[{"type": "TEXT",
                                  "expected": {"TextString": index}}])
