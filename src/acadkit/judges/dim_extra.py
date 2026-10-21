"""标注的"成组"判据：基线 / 连续 / 公差。

`judge_new_entity` 只能判"新增一个"，基线/连续一次出两个，所以单独写。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .base import Readback, close, new_entities, num, reopen_check, verdict


def judge_dim_set(rb: Readback, *, type_name: str = "ROTATEDDIMENSION",
                  expected: Sequence[float], total: Optional[float] = None,
                  tol: float = 1e-6) -> Dict[str, Any]:
    new = new_entities(rb, type_name)
    got = [num(e.get("Measurement")) for e in new]
    want = sorted(float(v) for v in expected)
    read = sorted(v for v in got if v is not None)
    matched = (len(read) == len(want)
               and all(close(a, b, tol) for a, b in zip(read, want)))
    checks: Dict[str, bool] = {
        "count": len(new) == len(expected),
        "measurements": matched,
    }
    detail: Dict[str, Any] = {"type": type_name,
                              "expected": want,
                              "read": got}
    if total is not None:
        s = sum(v for v in got if v is not None) if all(v is not None for v in got) else None
        checks["total"] = bool(s is not None and close(s, total, tol))
        detail["total_expected"] = total
        detail["total_read"] = s
    # 重开后每个新标注的 Measurement 不变（按句柄逐个回读）
    reopen_ok = rb.reopened is not None
    if reopen_ok:
        for e in new:
            ok, _ = reopen_check(rb, e, ("Measurement",))
            reopen_ok = reopen_ok and ok
    checks["reopen"] = bool(reopen_ok)
    return verdict(checks, detail, {"read": got, "counts": rb.memory.counts})


def judge_tolerance(rb: Readback, *, expected_measurement: float,
                    expected_override: str,
                    recorded: Dict[str, Any]) -> Dict[str, Any]:
    """公差：Measurement 不变 + TextOverride 读回 + DIMTOL/DIMTP/DIMTM 生效。"""
    new = new_entities(rb, "ROTATEDDIMENSION")
    ent = new[0] if len(new) == 1 else None
    meas = num(ent.get("Measurement")) if ent else None
    override = str(ent.get("TextOverride")) if ent else ""
    checks = {
        "count": len(new) == 1,
        "measurement": close(meas, expected_measurement, 1e-6),
        "text_override": override == expected_override,
        "dimtol": int(recorded.get("DIMTOL") or 0) == 1,
        "dimtp": close(recorded.get("DIMTP"), recorded.get("upper"), 1e-9),
        "dimtm": close(recorded.get("DIMTM"), recorded.get("lower"), 1e-9),
        "reopen": bool(rb.reopened is not None
                       and rb.reopened.count("ROTATEDDIMENSION")
                       == rb.memory.count("ROTATEDDIMENSION")),
    }
    upper = recorded.get("upper")
    lower = recorded.get("lower")
    if checks["reopen"] and ent is not None:
        checks["reopen"] = bool(reopen_check(rb, ent, ("Measurement",))[0])
    detail = {"measurement_read": meas,
              "text_override_read": override,
              "expected_override": expected_override,
              "dimtol": recorded.get("DIMTOL"),
              "dimtp": recorded.get("DIMTP"),
              "dimtm": recorded.get("DIMTM"),
              "upper": upper, "lower": lower}
    return verdict(checks, detail, {"entity": ent.attrs if ent else None,
                                    "recorded": recorded})

