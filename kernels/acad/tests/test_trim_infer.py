"""修剪/延伸与约束推断的离线测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.geom2d.trim import (CircleCutter, TrimError, cut_params,        # noqa: E402
                                 extend_segment, trim_segment)
from acadkit.solve.constraints import Point, Segment                         # noqa: E402
from acadkit.solve.infer import apply_inferred, infer_constraints            # noqa: E402


def close(a, b, tol=1e-9) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


# ── 修剪 ────────────────────────────────────────────────────────────
def test_cut_params_with_line() -> None:
    ts = cut_params((0, 0), (100, 0), [((40, -10), (40, 10))])
    assert len(ts) == 1 and abs(ts[0] - 0.4) < 1e-9


def test_trim_keep_start() -> None:
    got = trim_segment((0, 0), (100, 0), [((40, -10), (40, 10))], keep="start")
    assert len(got) == 1 and close(got[0][1], (40, 0))


def test_trim_keep_end() -> None:
    got = trim_segment((0, 0), (100, 0), [((40, -10), (40, 10))], keep="end")
    assert close(got[0][0], (40, 0)) and close(got[0][1], (100, 0))


def test_trim_middle_needs_two_cutters() -> None:
    cutters = [((20, -10), (20, 10)), ((60, -10), (60, 10))]
    got = trim_segment((0, 0), (100, 0), cutters, keep="middle")
    assert close(got[0][0], (20, 0)) and close(got[0][1], (60, 0))
    try:
        trim_segment((0, 0), (100, 0), [cutters[0]], keep="middle")
    except TrimError:
        pass
    else:
        raise AssertionError("单交点不应能取中段")


def test_trim_with_circle_cutter() -> None:
    """水平线穿过圆（r=10，圆心 (50,0)）→ 两个交点 40 与 60。"""
    ts = cut_params((0, 0), (100, 0), [CircleCutter((50, 0), 10)])
    assert len(ts) == 2
    assert abs(ts[0] - 0.4) < 1e-9 and abs(ts[1] - 0.6) < 1e-9


def test_trim_no_intersection_raises() -> None:
    try:
        trim_segment((0, 0), (10, 0), [((0, 50), (10, 50))])
    except TrimError:
        pass
    else:
        raise AssertionError("无交点应抛 TrimError")


# ── 延伸 ────────────────────────────────────────────────────────────
def test_extend_to_boundary() -> None:
    p1, p2 = (0.0, 0.0), (50.0, 0.0)
    got = extend_segment(p1, p2, [((120, -10), (120, 10))])
    assert close(got[0], p1) and close(got[1], (120, 0))


def test_extend_backwards() -> None:
    p1, p2 = (50.0, 0.0), (100.0, 0.0)
    got = extend_segment(p1, p2, [((10, -10), (10, 10))], which="start")
    assert close(got[0], (10, 0)) and close(got[1], p2)


def test_extend_without_boundary_raises() -> None:
    try:
        extend_segment((0, 0), (10, 0), [((0, 50), (10, 50))])
    except TrimError:
        pass
    else:
        raise AssertionError("无边界应抛 TrimError")


# ── 约束推断 ────────────────────────────────────────────────────────
def test_infer_horizontal_and_vertical() -> None:
    pts = {"a": Point("a", (0, 0)), "b": Point("b", (40, 0)),
           "c": Point("c", (40, 25))}
    segs = {"bottom": Segment("bottom", "a", "b"),
            "right": Segment("right", "b", "c")}
    got = infer_constraints(pts, segs)
    kinds = {item["constraint"].kind for item in got}
    assert "horizontal" in kinds and "vertical" in kinds


def test_infer_coincident() -> None:
    pts = {"a": Point("a", (0, 0)), "b": Point("b", (0, 0))}
    got = infer_constraints(pts, {})
    assert any(item["constraint"].kind == "coincident" for item in got)


def test_infer_parallel_lower_confidence() -> None:
    pts = {"a": Point("a", (0, 0)), "b": Point("b", (10, 5)),
           "c": Point("c", (0, 20)), "d": Point("d", (10, 25))}
    segs = {"s1": Segment("s1", "a", "b"), "s2": Segment("s2", "c", "d")}
    got = infer_constraints(pts, segs)
    par = [i for i in got if i["constraint"].kind == "parallel"]
    assert par and par[0]["confidence"] < 0.9, "平行推断置信度应偏低"
    kept = apply_inferred(pts, segs, got)
    assert not [c for c in kept if c.kind == "parallel"], "低置信度默认不落地"


def test_infer_respects_tolerance() -> None:
    pts = {"a": Point("a", (0, 0)), "b": Point("b", (40, 2))}
    segs = {"s": Segment("s", "a", "b")}
    got = infer_constraints(pts, segs, angle_tol_deg=0.5)
    assert not got, "倾斜 2.8° 不该被推断成水平"
