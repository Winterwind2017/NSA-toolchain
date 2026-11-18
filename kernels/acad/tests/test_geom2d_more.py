"""多边形（偏移/包含/孤岛）与 ACI 颜色的离线测试。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.geom2d.colors import aci_to_rgb, is_dark, rgb_to_aci          # noqa: E402
from acadkit.geom2d.polygon import (GeometryError, area, bulge_to_points,  # noqa: E402
                                    classify_islands, hatch_area, offset_polygon,
                                    point_in_polygon)

SQUARE = [(0, 0), (40, 0), (40, 40), (0, 40)]


def test_area_of_square() -> None:
    assert abs(area(SQUARE) - 1600) < 1e-9


def test_point_in_polygon() -> None:
    assert point_in_polygon((20, 20), SQUARE)
    assert not point_in_polygon((50, 20), SQUARE)


def test_offset_outward_grows_square() -> None:
    out = offset_polygon(SQUARE, 5.0)
    assert len(out) == 4, out
    assert abs(area(out) - 50 * 50) < 1e-6, area(out)


def test_offset_inward_shrinks_square() -> None:
    out = offset_polygon(SQUARE, -8.0)
    assert abs(area(out) - 24 * 24) < 1e-6, area(out)


def test_offset_inward_self_intersection_is_reported() -> None:
    """内缩超过半宽会自交——必须报错，不能给出乱结果。"""
    try:
        offset_polygon(SQUARE, -25.0)
    except GeometryError as exc:
        assert any(k in str(exc) for k in ("自交", "翻转", "内接圆")), str(exc)
    else:
        raise AssertionError("过度内缩应抛 GeometryError")


def test_offset_open_polyline() -> None:
    line = [(0, 0), (10, 0), (10, 10)]
    out = offset_polygon(line, 2.0, closed=False)
    assert len(out) == 3
    # 向外 = 右法向：第一条边沿 +x，右法向是 (0,-1) → 起点 y = -2
    assert abs(out[0][1] + 2.0) < 1e-9, out


def test_bulge_semicircle_length() -> None:
    """半圆（bulge=1）离散后，点到圆心距离都应等于半径。"""
    p1, p2 = (0.0, 0.0), (20.0, 0.0)
    pts = bulge_to_points(p1, p2, 1.0, steps=32)
    assert len(pts) == 32 and pts[-1] == p2
    center = (10.0, 0.0)
    for p in pts:
        assert abs(math.dist(p, center) - 10.0) < 0.2, p


def test_classify_islands_and_hatch_area() -> None:
    """外框 40×40，内孔 10×10（孔在外框内部）→ 净面积 1500。"""
    outer = SQUARE
    inner = [(10, 10), (20, 10), (20, 20), (10, 20)]
    metas = classify_islands([outer, inner])
    assert metas[0]["depth"] == 0 and not metas[0]["is_hole"]
    assert metas[1]["depth"] == 1 and metas[1]["is_hole"]
    assert abs(hatch_area([outer, inner]) - (1600 - 100)) < 1e-9


def test_aci_basic_colors() -> None:
    assert aci_to_rgb(1) == (255, 0, 0)
    assert aci_to_rgb(5) == (0, 0, 255)
    assert aci_to_rgb(250) == (51, 51, 51)
    assert aci_to_rgb(255) == (255, 255, 255)


def test_rgb_roundtrip_for_basic_colors() -> None:
    for idx in (1, 2, 3, 4, 5, 6):
        assert rgb_to_aci(aci_to_rgb(idx)) == idx


def test_aci_out_of_range() -> None:
    for bad in (0, 256, -1):
        try:
            aci_to_rgb(bad)
        except ValueError:
            continue
        raise AssertionError("越界索引应抛 ValueError：%r" % bad)


def test_is_dark() -> None:
    assert is_dark((0, 0, 0))
    assert not is_dark((255, 255, 255))
