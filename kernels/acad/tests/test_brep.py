"""离线 B-rep 与 STEP 出口测试（需要 cadquery；没有就 skip）。"""

from __future__ import annotations

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.brep import parts as B                                       # noqa: E402

cq_missing = B.backend() is None
pytestmark = pytest.mark.skipif(cq_missing, reason="没有 cadquery 后端")


def test_shaft_volume_matches_analytic() -> None:
    p = B.shaft(diameter=40, length=100)
    v = p.verify()
    assert v["ok"], v
    assert abs(v["got"] - math.pi * 20 ** 2 * 100) < 1e-3
    assert p.faces() == 3, "圆柱应恰好 3 个面"


def test_shaft_bbox() -> None:
    p = B.shaft(diameter=20, length=50)
    b = p.bbox()
    assert abs(b["xlen"] - 20) < 1e-6 and abs(b["ylen"] - 20) < 1e-6
    assert abs(b["zlen"] - 50) < 1e-6


def test_flange_with_bolt_holes() -> None:
    p = B.flange(outer_d=120, bore_d=40, thickness=10,
                 bolt_holes=[{"diameter": 10, "bcd": 90, "count": 4}])
    v = p.verify()
    assert v["ok"], v
    # 解析式：外圆 - 内孔 - 4 个螺栓孔
    expect = (math.pi * 60 ** 2 - math.pi * 20 ** 2) * 10 - 4 * math.pi * 5 ** 2 * 10
    assert abs(v["got"] - expect) < expect * 1e-9


def test_flange_rejects_bad_geometry() -> None:
    for kwargs in ({"outer_d": 40, "bore_d": 40, "thickness": 10},
                   {"outer_d": 100, "bore_d": 20, "thickness": 0},
                   {"outer_d": 100, "bore_d": 20, "thickness": 10,
                    "bolt_holes": [{"diameter": 10, "bcd": 120, "count": 4}]}):
        try:
            B.flange(**kwargs)
        except B.BrepError:
            continue
        raise AssertionError("非法几何应报错：%r" % (kwargs,))


def test_plate_with_holes() -> None:
    p = B.plate(length=200, width=100, thickness=8,
                holes=[{"x": -70, "y": 0, "diameter": 12},
                       {"x": 70, "y": 0, "diameter": 12}])
    v = p.verify()
    assert v["ok"], v
    expect = 200 * 100 * 8 - 2 * math.pi * 6 ** 2 * 8
    assert abs(v["got"] - expect) < expect * 1e-9


def test_plate_hole_outside_rejected() -> None:
    try:
        B.plate(length=100, width=50, thickness=5,
                holes=[{"x": 49, "y": 0, "diameter": 10}])
    except B.BrepError as exc:
        assert "超出板边" in str(exc)
    else:
        raise AssertionError("孔超出板边应报错")


def test_step_roundtrip_keeps_volume() -> None:
    d = tempfile.mkdtemp(prefix="brep_")
    p = B.shaft(diameter=30, length=60)
    out = B.roundtrip(p, os.path.join(d, "shaft.step"))
    assert out["ok"], out
    assert out["step"]["bytes"] > 1000
    assert out["back"]["solids"] == 1
    assert abs(out["back"]["volume"] - p.volume()) < 1.0


def test_step_export_missing_dir_raises() -> None:
    p = B.shaft(diameter=10, length=10)
    try:
        B.to_step(p, os.path.join(tempfile.gettempdir(), "no_such_dir_zzz", "a.step"))
    except B.BrepError as exc:
        assert "父目录" in str(exc)
    else:
        raise AssertionError("缺父目录应报错")


def test_stl_export_produces_file() -> None:
    d = tempfile.mkdtemp(prefix="brep_stl_")
    path = os.path.join(d, "shaft.stl")
    info = B.to_stl(B.shaft(diameter=20, length=20), path)
    assert os.path.getsize(path) > 200
    assert info["faces"] == 3


def test_backend_reports_name() -> None:
    assert B.backend() == "cadquery"
