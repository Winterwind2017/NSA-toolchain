"""曲线几何的离线测试（不需要 AutoCAD）。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.geom2d.curves import (GeometryError, chamfer, circle_circle,  # noqa: E402
                                   ellipse_line, fillet, line_circle, line_line)


def close(a, b, tol=1e-9) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def test_line_line_basic() -> None:
    got = line_line((0, 0), (10, 10), (0, 10), (10, 0))
    assert len(got) == 1 and close(got[0], (5, 5))


def test_line_line_parallel_has_no_unique_intersection() -> None:
    assert line_line((0, 0), (10, 0), (0, 5), (10, 5)) == []


def test_line_line_segments_respect_extent() -> None:
    # 无限长直线相交于 (5,5)，但两条短线段够不到
    assert line_line((0, 0), (2, 2), (0, 10), (2, 8)) == []
    assert line_line((0, 0), (2, 2), (0, 10), (2, 8), segments=False)


def test_line_circle_two_points() -> None:
    got = line_circle((-20, 5), (20, 5), (0, 0), 10)
    xs = sorted(p[0] for p in got)
    assert len(got) == 2
    assert abs(xs[0] + math.sqrt(75)) < 1e-9 and abs(xs[1] - math.sqrt(75)) < 1e-9


def test_line_circle_tangent_and_miss() -> None:
    assert len(line_circle((-20, 10), (20, 10), (0, 0), 10)) == 1
    assert line_circle((-20, 11), (20, 11), (0, 0), 10) == []


def test_circle_circle_two_and_none() -> None:
    got = circle_circle((0, 0), 5, (6, 0), 5)
    assert len(got) == 2
    for p in got:
        assert abs(math.dist(p, (0, 0)) - 5) < 1e-9
        assert abs(math.dist(p, (6, 0)) - 5) < 1e-9
    assert circle_circle((0, 0), 1, (10, 0), 1) == []


def test_circle_circle_degenerate_raises() -> None:
    for args in (((0, 0), 5, (0, 0), 5), ((0, 0), 5, (0, 0), 3)):
        try:
            circle_circle(*args)
        except GeometryError:
            pass
        else:
            raise AssertionError("同心/重合应抛 GeometryError")


def test_ellipse_line_hits_four_points_for_secant() -> None:
    """长直线穿过椭圆左右两侧 → 2 个交点（对称）。"""
    got = ellipse_line((0, 0), 20, 10, (-30, 0), (30, 0))
    xs = sorted(p[0] for p in got)
    assert len(got) == 2, got
    assert abs(xs[0] + 20) < 1e-6 and abs(xs[1] - 20) < 1e-6


def test_ellipse_line_miss() -> None:
    assert ellipse_line((0, 0), 20, 10, (-30, 15), (30, 15)) == []


def test_fillet_perpendicular() -> None:
    """直角 + R5：圆心 (5,5)，切点 (5,0) 与 (0,5)，扫掠 90°。"""
    got = fillet((0, 0), (100, 0), (0, 100), 5)
    assert close(got["center"], (5, 5), 1e-9)
    assert close(got["tangent1"], (5, 0), 1e-9)
    assert close(got["tangent2"], (0, 5), 1e-9)
    assert abs(got["sweep_rad"] - math.pi / 2) < 1e-9


def test_fillet_radius_too_large_raises() -> None:
    try:
        fillet((0, 0), (10, 0), (0, 10), 20)
    except GeometryError:
        pass
    else:
        raise AssertionError("切点越界应抛 GeometryError")


def test_fillet_parallel_raises() -> None:
    try:
        fillet((0, 0), (10, 0), (-10, 0), 2)
    except GeometryError:
        pass
    else:
        raise AssertionError("反向边应抛 GeometryError")


def test_chamfer_length() -> None:
    got = chamfer((0, 0), (100, 0), (0, 100), 8, 8)
    assert close(got["p1"], (8, 0), 1e-9)
    assert close(got["p2"], (0, 8), 1e-9)
    assert abs(got["length"] - 8 * math.sqrt(2)) < 1e-9


def test_chamfer_overrun_raises() -> None:
    try:
        chamfer((0, 0), (5, 0), (0, 100), 8, 8)
    except GeometryError:
        pass
    else:
        raise AssertionError("倒角越界应抛 GeometryError")
