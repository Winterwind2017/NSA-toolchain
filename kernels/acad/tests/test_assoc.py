"""关联标注模型的离线测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dxf.document import Entity, make_circle, make_line      # noqa: E402
from acadkit.model.assoc import (Anchor, AssocError, create,        # noqa: E402
                                 resolve_point, scan_stale)


def _ents() -> dict:
    line = make_line((0, 0), (40, 0), handle="L1")
    other = make_line((0, 20), (40, 20), handle="L2")
    circle = make_circle((100, 0), 10, handle="C1")
    return {"L1": line, "L2": other, "C1": circle}


def test_anchor_rejects_unknown_kind() -> None:
    try:
        Anchor("L1", kind="corner")
    except AssocError as exc:
        assert "未知锚点" in str(exc)
    else:
        raise AssertionError("未知锚点类型应报错")


def test_resolve_endpoints_and_midpoint() -> None:
    ents = _ents()
    assert resolve_point(ents, Anchor("L1", "endpoint")) == (0.0, 0.0, 0.0)
    assert resolve_point(ents, Anchor("L1", "endpoint2")) == (40.0, 0.0, 0.0)
    assert resolve_point(ents, Anchor("L1", "midpoint")) == (20.0, 0.0, 0.0)
    assert resolve_point(ents, Anchor("C1", "center")) == (100.0, 0.0, 0.0)


def test_resolve_missing_entity_raises() -> None:
    try:
        resolve_point(_ents(), Anchor("NOPE", "endpoint"))
    except AssocError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("引用缺失实体应报错")


def test_circle_has_no_endpoint() -> None:
    try:
        resolve_point(_ents(), Anchor("C1", "endpoint"))
    except AssocError as exc:
        assert "center" in str(exc) and "端点" in str(exc)
    else:
        raise AssertionError("圆不该有端点")


def test_midpoint_only_for_line() -> None:
    try:
        resolve_point(_ents(), Anchor("C1", "midpoint"))
    except AssocError as exc:
        assert "中点只支持" in str(exc)
    else:
        raise AssertionError("圆不该有中点")


def test_create_computes_measurement() -> None:
    dim = create("D1", _ents(), Anchor("L1", "endpoint"), Anchor("L2", "endpoint"))
    assert dim.measurement == 20.0


def test_stale_detection_after_geometry_moves() -> None:
    ents = _ents()
    dim = create("D1", ents, Anchor("L1", "endpoint"), Anchor("L2", "endpoint"))
    assert not dim.stale(ents)

    # 把 L2 整体上移 10 → 记录值 20 与实际 30 不符
    ents["L2"] = make_line((0, 30), (40, 30), handle="L2")
    assert dim.stale(ents)
    assert abs(dim.recompute(ents) - 30.0) < 1e-9

    report = scan_stale([dim], ents)
    assert report and report[0]["reason"] == "stale"
    assert report[0]["recorded"] == 20.0 and abs(report[0]["current"] - 30.0) < 1e-9


def test_scan_stale_reports_unresolved() -> None:
    ents = _ents()
    dim = create("D1", ents, Anchor("L1", "endpoint"), Anchor("L2", "endpoint"))
    ents.pop("L2")
    report = scan_stale([dim], ents)
    assert report[0]["reason"] == "unresolved"


def test_whole_anchor_uses_start_point() -> None:
    ents = _ents()
    assert resolve_point(ents, Anchor("L1", "whole")) == (0.0, 0.0, 0.0)


def test_dimension_with_3d_coordinates() -> None:
    """坐标带 Z 时距离仍按 XY 平面算（标注是平面量）。"""
    ents = {"A": Entity("LINE", [(0, "LINE"), (5, "A"), (10, "0"), (20, "0"), (30, "99"),
                                 (11, "10"), (21, "0"), (31, "99")])}
    assert resolve_point(ents, Anchor("A", "endpoint"))[2] == 99.0
    dim = create("D", ents, Anchor("A", "endpoint"), Anchor("A", "endpoint2"))
    assert abs(dim.measurement - 10.0) < 1e-9
