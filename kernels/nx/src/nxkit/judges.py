"""判据：把 `expect` 和 NX 里读回的 `reads` 逐项比对。

规则只有一条：**判据只看读数**。返回值/异常只用来解释失败，不参与通过判定。
"""

from __future__ import annotations

from . import caps

ABS_TOL = 0.5          # 体积/面积（mm 量级）容忍 0.5 mm³
REL_TOL = 1e-9


def _tol(want: float) -> float:
    """按量级给容差：大数（体积/面积）0.5；个位数 1e-3；比率 1e-6。

    早期版本对所有数值都用 0.5 绝对容差，导致 "视图缩放 0.59 vs 期望 0.5"
    也会判通过——那是错判，这里按量级收紧。
    """
    a = abs(want)
    if a >= 100.0:
        return ABS_TOL
    if a >= 1.0:
        return 1e-3
    return 1e-6


def _close(got, want) -> bool:
    try:
        g = float(got)
        w = float(want)
    except (TypeError, ValueError):
        return got == want
    return abs(g - w) <= max(_tol(w), abs(w) * REL_TOL)


def compare(reads: dict, expect: dict) -> list[dict]:
    checks = []
    for key, want in expect.items():
        got = reads.get(key)
        if isinstance(want, dict) and {"min", "max"} <= set(want):
            ok = got is not None and want["min"] <= float(got) <= want["max"]
        elif isinstance(want, (int, float)):
            ok = _close(got, want)
        else:
            ok = got == want
        checks.append({"check": key, "want": want, "got": got, "ok": ok})
    return checks


def verdict(checks: list[dict]) -> bool:
    return bool(checks) and all(c["ok"] for c in checks)


def judge_record(cap: caps.Cap, record: dict) -> dict:
    reads = record.get("reads") or {}
    checks = compare(reads, cap.expect)
    # L4：要求在重开后仍读得到同样的体积
    if cap.reopen and "volume_mm3" in cap.expect:
        v = reads.get("volume_mm3")
        v2 = reads.get("volume_reopened")
        if v2 is None:
            checks.append({"check": "volume_reopened", "want": v, "got": None,
                           "ok": False})
        else:
            checks.append({"check": "volume_reopened_equal", "want": v,
                           "got": v2, "ok": _close(v2, v)})
    ok = verdict(checks) and bool(record.get("ok"))
    return {"id": cap.id, "ok": ok, "checks": checks,
            "errors": record.get("errors") or [],
            "seconds": record.get("seconds")}
