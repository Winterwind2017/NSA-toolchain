"""3D 实体 / 布尔 / 剖切判据（JUDGE_SPEC 2.6 的 L1–L4）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Readback, new_entities, num, rel_close, verdict


def judge_solids(rb: Readback, *, expected: List[float],
                 rel: float = 0.01) -> Dict[str, Any]:
    """一组 3DSOLID 的体积逐个对照（与输入顺序无关的贪心匹配）。"""
    news = new_entities(rb, "3DSOLID")
    vols: List[Optional[float]] = [num(e.get("Volume")) for e in news]
    remaining = list(expected)
    matched: List[Optional[float]] = []
    checks: Dict[str, bool] = {"count": len(news) == len(expected)}
    detail: Dict[str, Any] = {"expected": [round(v, 6) for v in expected],
                              "read": vols, "pairs": []}
    for want in expected:
        hit = None
        for i, got in enumerate(vols):
            if got is None:
                continue
            if abs(got - want) / max(abs(want), 1e-12) <= rel:
                hit = i
                break
        if hit is None:
            checks["volume:%g" % want] = False
            detail["pairs"].append({"expected": want, "matched": None})
        else:
            checks["volume:%g" % want] = True
            detail["pairs"].append({"expected": want, "matched": vols[hit]})
            vols[hit] = None
    checks["type"] = bool(news) and all(
        e.get("ObjectName") == "AcDb3dSolid" for e in news)
    re_ok = bool(rb.reopened is not None
                 and rb.reopened.count("3DSOLID") == rb.memory.count("3DSOLID"))
    checks["reopen"] = re_ok
    return verdict(checks, detail, {"before": rb.before.counts,
                                    "memory": rb.memory.counts})


def judge_boolean(rb: Readback, *, expected_volume: float,
                  rel: float = 0.05) -> Dict[str, Any]:
    """布尔后实体数 2→1，且体积等于解析值。"""
    news = new_entities(rb, "3DSOLID")
    vol = num(news[0].get("Volume")) if len(news) == 1 else None
    checks = {
        "count_before_two": rb.before.count("3DSOLID") == 0,
        "count_after_one": rb.memory.count("3DSOLID") == 1 and len(news) == 1,
        "volume": rel_close(vol, expected_volume, rel),
    }
    re_ok = bool(rb.reopened is not None
                 and rb.reopened.count("3DSOLID") == 1)
    if re_ok and rb.reopened is not None:
        re_ents = rb.reopened.of_type("3DSOLID")
        re_ok = bool(re_ents) and rel_close(num(re_ents[0].get("Volume")),
                                            expected_volume, rel)
    checks["reopen"] = re_ok
    detail = {"volume_expected": round(expected_volume, 6), "volume_read": vol,
              "counts_before": rb.before.counts, "counts_memory": rb.memory.counts}
    return verdict(checks, detail, {"entity": news[0].attrs if news else None})


def judge_slice(rb: Readback, *, expected_total: float,
                rel: float = 0.02) -> Dict[str, Any]:
    """剖切后应是两个实体，体积之和 = 原体积。"""
    news = new_entities(rb, "3DSOLID")
    vols = [num(e.get("Volume")) for e in news]
    total = sum(v for v in vols if v is not None) if all(v is not None for v in vols) else None
    checks = {
        "two_pieces": len(news) == 2,
        "each_positive": all((v or 0) > 0 for v in vols),
        "sum": rel_close(total, expected_total, rel),
    }
    detail = {"expected_total": round(expected_total, 6), "pieces": vols,
              "sum_read": total}
    return verdict(checks, detail, {"before": rb.before.counts,
                                    "memory": rb.memory.counts})
