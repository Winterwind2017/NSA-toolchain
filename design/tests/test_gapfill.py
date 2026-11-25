"""对方有、这里补上的离线能力。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gapfill import (  # noqa: E402
    cjk_text_issues,
    copy_target,
    edges_in_band,
    helix_length,
    holes_from_cylinders,
    motion_samples_ok,
    parse_tolerance,
    polygon_area,
    reject_false_success,
    rename_preview,
    spur_gear_polygon,
    sprocket_pitch_diameter,
    write_box_stl,
    write_preview_page,
)


def test_false_success_needs_a_geometry_change():
    assert reject_false_success(True, 100.0, 100.0)["ok"] is False
    assert reject_false_success(True, 100.0, 80.0)["ok"] is True
    assert reject_false_success(False, 100.0, 80.0)["ok"] is False


def test_tolerance_holes_rename_and_copy():
    assert parse_tolerance("10±0.05")["lower"] == -0.05
    assert parse_tolerance("10 +0.02/-0.01")["upper"] == 0.02
    holes = holes_from_cylinders([
        {"radius_mm": 4, "x": 0, "y": 0},
        {"radius_mm": 4, "x": 20, "y": 0},
    ])
    assert holes["holes"][0]["count"] == 2
    assert holes["holes"][0]["diameter_mm"] == 8
    bad = rename_preview(["a"], {"a": ""})
    assert bad["ok"] is False
    assert copy_target(r"D:\a\part.sldprt", r"D:\a\part.sldprt")["ok"] is False
    assert copy_target(r"D:\a\part.sldprt", r"D:\b\part.sldprt")["ok"] is True


def test_gear_spring_sprocket_and_edges():
    points = spur_gear_polygon(2.0, 12)
    addendum = 2.0 * (12 + 2) / 2.0
    assert polygon_area(points) > 0
    assert max(math.hypot(x, y) for x, y in points) == addendum
    assert abs(sprocket_pitch_diameter(20, 12.7) - 12.7 / math.sin(math.pi / 20)) < 1e-9
    length = helix_length(10.0, 5.0, 3.0)
    assert length > 3 * 2 * math.pi * 10
    picked = edges_in_band(
        [{"length_mm": 5}, {"length_mm": 40}, {"length_mm": 12}], 10, 20)
    assert picked == [{"length_mm": 12}]


def test_cjk_motion_stl_and_preview(tmp_path):
    issues = cjk_text_issues(
        [{"text": "标题", "style": "Standard", "x": 0, "y": 0, "height": 5},
         {"text": "标题", "style": "CN", "x": 1, "y": 1, "height": 5}],
        {"CN": {"bigfont": "gbcbig.shx"}, "Standard": {}},
    )
    rules = {item["rule"] for item in issues}
    assert "cjk_without_bigfont" in rules
    assert "text_overlap" in rules
    assert motion_samples_ok([0, 1], out_of_date=True)["ok"] is False
    assert motion_samples_ok([0, 1], out_of_date=False)["ok"] is True
    stl = tmp_path / "box.stl"
    write_box_stl(str(stl), 10)
    assert stl.read_text(encoding="ascii").startswith("solid nsa_box")
    page = write_preview_page(str(tmp_path), ["frame_000.bmp"])
    assert "frame_000.bmp" in open(page, encoding="utf-8").read()
