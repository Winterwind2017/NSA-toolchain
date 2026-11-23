"""DFM（可制造性）规则测试：合规件必须零告警，违规件必须命中对应规则。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dfm.rules import (DfmError, check_any, check_injection,      # noqa: E402
                               check_milling, check_print3d, check_sheet_metal)


def rules(rep) -> list:
    return [f.rule for f in rep.findings]


# ── 钣金 ────────────────────────────────────────────────────────────
def test_sheet_metal_compliant_has_no_findings() -> None:
    rep = check_sheet_metal(thickness=2.0, bend_radius=2.0,
                            holes=[{"diameter": 6.0, "distance_to_bend": 20.0}],
                            min_flange=10.0)
    assert rep.findings == [], rep.to_text()
    assert rep.ok


def test_hole_too_close_to_bend_is_error() -> None:
    rep = check_sheet_metal(thickness=2.0, bend_radius=2.0,
                            holes=[{"diameter": 6.0, "distance_to_bend": 5.0}])
    assert "hole_too_close_to_bend" in rules(rep)
    assert not rep.ok
    assert "孔心外移" in rep.findings[0].fix


def test_hole_smaller_than_thickness_warns() -> None:
    rep = check_sheet_metal(thickness=3.0, bend_radius=3.0,
                            holes=[{"diameter": 2.0, "distance_to_bend": 30.0}])
    assert "hole_smaller_than_thickness" in rules(rep)
    assert rep.ok, "只是告警，不应判失败"


def test_bend_radius_invalid() -> None:
    rep = check_sheet_metal(thickness=2.0, bend_radius=0.0)
    assert "bend_radius_too_small" in rules(rep)
    assert not rep.ok


def test_flange_too_short() -> None:
    rep = check_sheet_metal(thickness=2.0, bend_radius=2.0, min_flange=3.0)
    assert "flange_too_short" in rules(rep)


def test_sheet_metal_rejects_non_finite() -> None:
    try:
        check_sheet_metal(thickness=float("nan"), bend_radius=1.0)
    except DfmError as exc:
        assert "非有限" in str(exc) or "数值" in str(exc)
    else:
        raise AssertionError("NaN 板厚应报错")


# ── 铣削 ────────────────────────────────────────────────────────────
def test_milling_compliant() -> None:
    rep = check_milling(tool_diameter=10.0,
                        pockets=[{"width": 30.0, "depth": 30.0, "corner_radius": 5.0}])
    assert rep.findings == [], rep.to_text()


def test_milling_narrow_pocket_and_small_corner() -> None:
    rep = check_milling(tool_diameter=10.0,
                        pockets=[{"width": 8.0, "depth": 8.0, "corner_radius": 2.0}])
    rs = rules(rep)
    assert "pocket_narrower_than_tool" in rs
    assert "corner_radius_too_small" in rs


def test_milling_depth_ratio() -> None:
    rep = check_milling(tool_diameter=6.0,
                        pockets=[{"width": 10.0, "depth": 100.0, "corner_radius": 3.0}])
    assert "depth_ratio_too_high" in rules(rep)


# ── 注塑 ────────────────────────────────────────────────────────────
def test_injection_compliant() -> None:
    rep = check_injection(walls=[2.0, 2.2], draft_deg=1.5,
                          ribs=[{"thickness": 1.0, "height": 2.5}])
    assert rep.findings == [], rep.to_text()


def test_injection_thin_and_thick_walls() -> None:
    thin = check_injection(walls=[0.5], draft_deg=1.0)
    assert "wall_too_thin" in rules(thin)
    assert not thin.ok
    thick = check_injection(walls=[5.0], draft_deg=1.0)
    assert "wall_too_thick" in rules(thick)


def test_injection_wall_variation_and_draft() -> None:
    rep = check_injection(walls=[1.0, 3.0], draft_deg=0.3)
    rs = rules(rep)
    assert "wall_variation" in rs
    assert "draft_too_small" in rs


def test_injection_rib_rules() -> None:
    rep = check_injection(walls=[2.0], draft_deg=1.5,
                          ribs=[{"thickness": 2.0, "height": 9.0}])
    rs = rules(rep)
    assert "rib_too_thick" in rs
    assert "rib_tall" in " ".join(rs) or "rib_too_tall" in rs


# ── 3D 打印 ─────────────────────────────────────────────────────────
def test_print3d_compliant() -> None:
    rep = check_print3d(min_wall=1.0, overhang_deg=40.0, nozzle=0.4, holes=[1.5])
    assert rep.findings == [], rep.to_text()


def test_print3d_thin_wall_and_steep_overhang() -> None:
    rep = check_print3d(min_wall=0.6, overhang_deg=60.0, nozzle=0.4, holes=[0.5])
    rs = rules(rep)
    assert "wall_thin_for_nozzle" in rs
    assert "overhang_too_steep" in rs
    assert "hole_below_nozzle" in rs


# ── 分发 ────────────────────────────────────────────────────────────
def test_check_any_dispatch_and_unknown() -> None:
    rep = check_any("sheet_metal", thickness=2.0, bend_radius=2.0)
    assert rep.process == "sheet-metal"
    try:
        check_any("casting")
    except DfmError as exc:
        assert "未知工艺" in str(exc)
    else:
        raise AssertionError("未知工艺应报错")


def test_report_text_contains_fix() -> None:
    rep = check_milling(tool_diameter=10.0,
                        pockets=[{"width": 8.0, "depth": 8.0, "corner_radius": 1.0}])
    text = rep.to_text()
    assert "→" in text and "pocket_narrower_than_tool" in text
