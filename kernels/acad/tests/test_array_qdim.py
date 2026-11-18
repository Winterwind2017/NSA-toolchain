"""阵列与快速标注规划的离线测试。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.model.array import (ArrayError, along_path, plan_qdim,     # noqa: E402
                                 polar, rectangular)


# ── 矩形阵列 ────────────────────────────────────────────────────────
def test_rectangular_layout() -> None:
    inst = rectangular(2, 3, row_spacing=25, col_spacing=40)
    assert len(inst) == 6
    assert [(i.dx, i.dy) for i in inst[:3]] == [(0, 0), (40, 0), (80, 0)]
    assert [(i.dx, i.dy) for i in inst[3:]] == [(0, 25), (40, 25), (80, 25)]
    assert [i.index for i in inst] == list(range(6))


def test_rectangular_rejects_zero_counts() -> None:
    for rows, cols in ((0, 3), (3, 0), (-1, 2)):
        try:
            rectangular(rows, cols, 10, 10)
        except ArrayError:
            continue
        raise AssertionError("行列为 0 应报错：%r,%r" % (rows, cols))


def test_rectangular_rejects_zero_spacing_when_needed() -> None:
    assert rectangular(1, 1, 0, 0)                      # 单实例允许 0 间距
    try:
        rectangular(2, 1, 0, 10)
    except ArrayError as exc:
        assert "行间距" in str(exc)
    else:
        raise AssertionError("多行 0 间距应报错")


# ── 环形阵列 ────────────────────────────────────────────────────────
def test_polar_full_circle() -> None:
    inst = polar(4, radius=10)
    assert len(inst) == 4
    pts = [(round(i.dx, 6), round(i.dy, 6)) for i in inst]
    assert pts[0] == (10.0, 0.0)
    assert pts[1][0] == 0.0 and abs(pts[1][1] - 10.0) < 1e-6
    # 相邻夹角 90°
    assert abs(inst[1].rotation_deg - 90.0) < 1e-9


def test_polar_single_and_validation() -> None:
    assert polar(1) == [type(polar(1)[0])(0, 0.0, 0.0)]
    try:
        polar(0)
    except ArrayError:
        pass
    else:
        raise AssertionError("数量 0 应报错")


def test_polar_partial_arc_spacing() -> None:
    inst = polar(3, radius=10, total_angle_deg=90, rotate_items=False)
    assert abs(inst[1].rotation_deg) < 1e-9
    a1 = math.degrees(math.atan2(inst[1].dy, inst[1].dx))
    a2 = math.degrees(math.atan2(inst[2].dy, inst[2].dx))
    assert abs(a1 - 45.0) < 1e-6 and abs(a2 - 90.0) < 1e-6


# ── 沿路径 ──────────────────────────────────────────────────────────
def test_along_path_straight() -> None:
    inst = along_path([(0, 0), (100, 0)], 5)
    assert [round(i.dx, 6) for i in inst] == [0.0, 25.0, 50.0, 75.0, 100.0]


def test_along_path_elbow_interpolates() -> None:
    inst = along_path([(0, 0), (50, 0), (50, 50)], 3)
    assert (round(inst[1].dx, 6), round(inst[1].dy, 6)) == (50.0, 0.0)


def test_along_path_closed() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    inst = along_path(square, 4, closed=True)
    assert len(inst) == 4 and (round(inst[0].dx, 6), round(inst[0].dy, 6)) == (0.0, 0.0)


def test_along_path_validation() -> None:
    for pts, n in (([(0, 0), (1, 0)], 1), ([(0, 0)], 2), ([(0, 0), (0, 0)], 2)):
        try:
            along_path(pts, n)
        except ArrayError:
            continue
        raise AssertionError("非法参数应报错：%r,%r" % (pts, n))


# ── 快速标注规划 ────────────────────────────────────────────────────
def test_qdim_continuous_chain() -> None:
    segs = [((0, 0), (10, 0)), ((10, 0), (25, 0)), ((25, 0), (40, 0))]
    plans = plan_qdim(segs, offset=8)
    cont = [p for p in plans if p.kind == "continuous"]
    assert len(cont) == 1 and cont[0].segments == [0, 1, 2]
    assert abs(cont[0].dim_line_y - 8.0) < 1e-9


def test_qdim_baseline_group() -> None:
    """同一起点、不同长度的两条 → 基线标注。"""
    segs = [((0, 0), (40, 0)), ((0, 0), (60, 0))]
    plans = plan_qdim(segs, offset=10)
    base = [p for p in plans if p.kind == "baseline"]
    assert base and base[0].segments == [0, 1]


def test_qdim_ignores_slanted_edges() -> None:
    segs = [((0, 0), (10, 10)), ((0, 0), (20, 20))]
    assert plan_qdim(segs) == [], "斜边不参与 QDIM"


def test_qdim_vertical_axis() -> None:
    segs = [((0, 0), (0, 20)), ((0, 20), (0, 35))]
    plans = plan_qdim(segs)
    assert plans and plans[0].axis == "vertical"


def test_qdim_rejects_bad_offset() -> None:
    try:
        plan_qdim([((0, 0), (10, 0)), ((10, 0), (20, 0))], offset=0)
    except ArrayError:
        pass
    else:
        raise AssertionError("偏移 0 应报错")
