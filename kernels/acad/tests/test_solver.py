"""约束求解器的离线测试（不需要 AutoCAD）。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.solve.constraints import (Constraint, Point, Problem, Segment,  # noqa: E402
                                       evaluate_expr, solve)


def _segment_problem(length_start: float, target: float) -> Problem:
    pts = {"a": Point("a", (0.0, 0.0)), "b": Point("b", (length_start, 0.0))}
    segs = {"s": Segment("s", "a", "b")}
    cons = [Constraint("c1", "horizontal", points=("a", "b")),
            Constraint("c2", "distance", points=("a", "b"), value=target)]
    return Problem(pts, segs, cons)


def test_distance_converges() -> None:
    p = _segment_problem(50.0, 40.0)
    res = solve(p)
    assert res.ok, res.message
    got = math.dist(res.values["a"], res.values["b"])
    assert abs(got - 40.0) < 1e-6, got
    # 2 点 = 4 个变量；水平(1) + 距离(1) → 秩 2，剩 2 个平移自由度
    assert res.dof == 2, res.dof


def test_underconstrained_reports_dof() -> None:
    """只给"水平"不给距离：欠约束，dof 应为 3（4 个变量 − 1 条秩）。"""
    pts = {"a": Point("a", (0.0, 0.0)), "b": Point("b", (10.0, 5.0))}
    p = Problem(pts, {"s": Segment("s", "a", "b")},
                [Constraint("c1", "horizontal", points=("a", "b"))])
    res = solve(p)
    assert res.ok
    assert res.dof == 3, res.dof


def test_rectangle_with_constraints() -> None:
    """4 点矩形：水平/垂直 + 两个尺寸 → 解出 40×25。"""
    pts = {
        "p1": Point("p1", (0.0, 0.0), fixed=True),
        "p2": Point("p2", (33.0, 2.0)),
        "p3": Point("p3", (37.0, 22.0)),
        "p4": Point("p4", (1.0, 26.0)),
    }
    segs = {
        "bottom": Segment("bottom", "p1", "p2"),
        "right": Segment("right", "p2", "p3"),
        "top": Segment("top", "p3", "p4"),
        "left": Segment("left", "p4", "p1"),
    }
    cons = [
        Constraint("h1", "horizontal", points=("p1", "p2")),
        Constraint("h2", "horizontal", points=("p4", "p3")),
        Constraint("v1", "vertical", points=("p2", "p3")),
        Constraint("v2", "vertical", points=("p1", "p4")),
        Constraint("d1", "distance", points=("p1", "p2"), value=40.0),
        Constraint("d2", "distance", points=("p2", "p3"), value=25.0),
    ]
    p = Problem(pts, segs, cons)
    res = solve(p)
    assert res.ok, res.message
    assert abs(math.dist(res.values["p1"], res.values["p2"]) - 40.0) < 1e-6
    assert abs(math.dist(res.values["p2"], res.values["p3"]) - 25.0) < 1e-6
    # 矩形闭合性：对角相等
    assert abs(math.dist(res.values["p1"], res.values["p3"])
               - math.dist(res.values["p2"], res.values["p4"])) < 1e-6


def test_conflicting_constraints_fail_loudly() -> None:
    """同一条边要求 40 和 60：必须明确失败，不许返回"差不多"。"""
    pts = {"a": Point("a", (0.0, 0.0)), "b": Point("b", (50.0, 0.0))}
    cons = [Constraint("c1", "distance", points=("a", "b"), value=40.0),
            Constraint("c2", "distance", points=("a", "b"), value=60.0)]
    res = solve(Problem(pts, {}, cons))
    assert not res.ok, "冲突约束不该被判成功"
    assert res.residual_norm > 1e-3


def test_perpendicular_and_equal_length() -> None:
    pts = {
        "a": Point("a", (0.0, 0.0)),
        "b": Point("b", (30.0, 3.0)),
        "c": Point("c", (2.0, 40.0)),
    }
    segs = {"s1": Segment("s1", "a", "b"), "s2": Segment("s2", "a", "c")}
    cons = [
        Constraint("fixed_a", "fixed", points=("a",), value=0.0, value_y=0.0),
        Constraint("perp", "perpendicular", segments=("s1", "s2")),
        Constraint("eq", "equal_length", segments=("s1", "s2")),
        Constraint("len", "distance", points=("a", "b"), value=30.0),
    ]
    res = solve(Problem(pts, segs, cons))
    assert res.ok, res.message
    v1 = (res.values["b"][0] - res.values["a"][0], res.values["b"][1] - res.values["a"][1])
    v2 = (res.values["c"][0] - res.values["a"][0], res.values["c"][1] - res.values["a"][1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    assert abs(dot) < 1e-6, dot
    assert abs(math.dist(res.values["a"], res.values["b"])
               - math.dist(res.values["a"], res.values["c"])) < 1e-6


def test_fixed_point_does_not_move() -> None:
    pts = {"a": Point("a", (5.0, 7.0), fixed=True), "b": Point("b", (1.0, 1.0))}
    cons = [Constraint("c", "distance", points=("a", "b"), value=10.0)]
    res = solve(Problem(pts, {}, cons))
    assert res.ok
    assert res.values["a"] == (5.0, 7.0)
    assert abs(math.dist(res.values["a"], res.values["b"]) - 10.0) < 1e-6


def test_expr_arithmetic() -> None:
    assert evaluate_expr("d1/2 + 5", {"d1": 40.0}) == 25.0
    assert evaluate_expr("(a + b) * 2", {"a": 3.0, "b": 4.0}) == 14.0
    try:
        evaluate_expr("__import__('os')", {})
    except ValueError:
        pass
    else:
        raise AssertionError("表达式求值不该允许任意代码")
