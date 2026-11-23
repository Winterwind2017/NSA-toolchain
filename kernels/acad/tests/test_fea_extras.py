"""参数扫描 / 法兰简化校核 / FEA+DFM 合成结论的测试。"""

from __future__ import annotations

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dfm.rules import Finding, Report, check_milling           # noqa: E402
from acadkit.fea import combined as CB                                # noqa: E402
from acadkit.fea import flange as FL                                  # noqa: E402
from acadkit.fea import mesh as M                                     # noqa: E402
from acadkit.fea import runner as R                                   # noqa: E402
from acadkit.fea import sweep as SW                                   # noqa: E402

has_bridge = M.gmsh_version() is not None and R.find_ccx() is not None
try:
    from acadkit.brep import parts as B
    has_brep = True
except Exception:                                     # noqa: BLE001
    has_brep = False


# ── 法兰简化校核（纯公式，无需 gmsh/ccx）────────────────────────────
def test_flange_compliant_has_no_findings() -> None:
    rep = FL.flange_check(outer_d=200, bore_d=60, thickness=24, bolt_count=8,
                          bolt_d=12, bcd=150, preload_per_bolt=15000,
                          sigma_allow=140, bearing_allow=200)
    assert rep.findings == [], rep.to_text()
    assert rep.ok


def test_flange_over_preload_is_error() -> None:
    rep = FL.flange_check(outer_d=200, bore_d=60, thickness=24, bolt_count=8,
                          bolt_d=12, bcd=150, preload_per_bolt=200000,
                          sigma_allow=140, bearing_allow=200)
    rules = [f.rule for f in rep.findings]
    assert "bearing_overstress" in rules
    assert "flange_bending_overstress" in rules
    assert not rep.ok


def test_flange_thin_wall_needs_thicker() -> None:
    rep = FL.flange_check(outer_d=200, bore_d=60, thickness=8, bolt_count=8,
                          bolt_d=12, bcd=150, preload_per_bolt=20000,
                          sigma_allow=140)
    hit = [f for f in rep.findings if f.rule == "flange_bending_overstress"]
    assert hit, rep.to_text()
    assert "加厚到" in hit[0].fix


def test_flange_marginal_is_warn_only() -> None:
    # 让弯曲应力落在 80%~100% 许用之间：F=18000 → σ≈114.6 MPa / 140 = 82%
    rep = FL.flange_check(outer_d=200, bore_d=60, thickness=20, bolt_count=8,
                          bolt_d=12, bcd=150, preload_per_bolt=18000,
                          sigma_allow=140)
    rules = [f.rule for f in rep.findings]
    assert "flange_bending_marginal" in rules
    assert not any(f.severity == "error" for f in rep.findings)


def test_flange_edge_margin_and_bolt_circle() -> None:
    rep = FL.flange_check(outer_d=160, bore_d=50, thickness=20, bolt_count=6,
                          bolt_d=12, bcd=150, preload_per_bolt=8000)
    rules = [f.rule for f in rep.findings]
    assert "bolt_circle_outside" in rules
    assert "bolt_edge_margin" in rules


def test_flange_rejects_bad_input() -> None:
    for kw in ({"outer_d": 100, "bore_d": 120, "thickness": 10},
               {"outer_d": 200, "bore_d": 60, "thickness": 0},
               {"outer_d": 200, "bore_d": 60, "thickness": 10, "bolt_count": 0}):
        base = dict(bolt_count=8, bolt_d=12, bcd=150, preload_per_bolt=8000)
        base.update(kw)
        try:
            FL.flange_check(**base)
        except ValueError:
            continue
        raise AssertionError("非法输入应报错：%r" % (kw,))


# ── FEA + DFM 合成 ────────────────────────────────────────────────
def _fake_fea(stress: float, disp: float) -> dict:
    return {"stage": "done", "stress_nominal": stress, "measured": -disp}


def test_combined_pass_when_strong_and_makeable() -> None:
    dfm = check_milling(tool_diameter=10, pockets=[{"width": 30, "depth": 20,
                                                    "corner_radius": 6}])
    c = CB.combine(_fake_fea(30.0, 0.1), sigma_allow=140, dfm=dfm,
                   deflection_limit=0.5, concentration=2.0)
    assert c.verdict == "pass" and c.ok
    assert c.safety_factor > 1.5
    assert "结论：pass" in c.to_text()


def test_combined_weak_when_stress_high() -> None:
    c = CB.combine(_fake_fea(60.0, 0.1), sigma_allow=140, concentration=3.0)
    # peak = 180 > 140 → 不够
    assert c.verdict == "weak" and not c.strong_enough
    assert any(f.rule == "strength_insufficient" for f in c.fea)


def test_combined_unmakable_and_both() -> None:
    bad_dfm = check_milling(tool_diameter=10, pockets=[{"width": 8, "depth": 60,
                                                        "corner_radius": 2}])
    assert not bad_dfm.ok
    c1 = CB.combine(_fake_fea(20.0, 0.1), sigma_allow=140, dfm=bad_dfm)
    assert c1.verdict == "unmakable" and not c1.makeable
    c2 = CB.combine(_fake_fea(60.0, 0.1), sigma_allow=140, dfm=bad_dfm,
                    concentration=3.0)
    assert c2.verdict == "both"


def test_combined_deflection_limit_fails_strength_flag() -> None:
    c = CB.combine(_fake_fea(10.0, 1.0), sigma_allow=140, deflection_limit=0.2)
    assert c.verdict == "weak"
    assert any(f.rule == "deflection_exceeded" for f in c.fea)


def test_combined_errors() -> None:
    with pytest.raises(M.FeaError):
        CB.combine({"stage": "solve"}, sigma_allow=140)
    with pytest.raises(M.FeaError):
        CB.combine({"stage": "done", "stress_nominal": 0.0, "measured": 0.1},
                   sigma_allow=140)
    with pytest.raises(M.FeaError):
        CB.combine(_fake_fea(10.0, 0.1), sigma_allow=0)


def test_to_report_merges_findings() -> None:
    c = CB.combine(_fake_fea(60.0, 0.1), sigma_allow=140, concentration=3.0)
    rep = CB.to_report(c)
    assert isinstance(rep, Report)
    assert not rep.ok
    assert any(f.rule in ("strength_insufficient", "overall_not_pass")
               for f in rep.findings)


# ── 参数扫描 ──────────────────────────────────────────────────────
def test_sweep_requires_values() -> None:
    with pytest.raises(M.FeaError):
        SW.sweep(factory=lambda v: None, param="t", values=[], case="axial",
                 force=1, E=1, nu=0, mesh_size=1, tol=1e-2, workdir=tempfile.gettempdir())


def test_sweep_rejects_unknown_case() -> None:
    with pytest.raises(M.FeaError):
        SW.sweep(factory=lambda v: None, param="t", values=[1.0], case="buckling",
                 force=1, E=1, nu=0, mesh_size=1, tol=1e-2, workdir=tempfile.gettempdir())


def test_pick_min_requires_target() -> None:
    sw = SW.Sweep(param="t", case="axial")
    with pytest.raises(M.FeaError):
        SW.pick_min(sw)


def test_pick_min_and_csv_on_synthetic_sweep() -> None:
    sw = SW.Sweep(param="thickness", case="cantilever")
    for t, d in ((6, 0.40), (8, 0.29), (10, 0.22), (12, 0.18)):
        sw.points.append(SW.Point(value=t, ok=True, measured=d, expected=d,
                                  relative_error=0.0, stress_nominal=100.0 / t,
                                  slenderness=200 / t, volume_error=0.0))
    assert SW.pick_min(sw, max_deflection=0.25) == 10
    assert SW.pick_min(sw, max_deflection=0.1) is None
    assert SW.pick_min(sw, max_stress=14.0) == 8      # stress=100/t → t≥7.14
    path = os.path.join(tempfile.mkdtemp(prefix="csv_"), "sweep.csv")
    sw.to_csv(path)
    text = open(path, encoding="utf-8").read().splitlines()
    assert text[0].startswith("param,value,ok")
    assert len(text) == 5
    assert "扫描 thickness" in sw.to_text()
    assert sw.monotonic(decreasing=True)


@pytest.mark.skipif(not (has_bridge and has_brep), reason="缺 brep/gmsh/ccx")
def test_part_mesh_refuses_oversized_grid() -> None:
    """薄板 + 细网格会到百万单元 → 必须在划网格前拒算（否则 ccx 超时）。"""
    from acadkit.fea import brep_bridge as BB
    try:
        BB.part_mesh(B.plate(length=200, width=100, thickness=0.8), mesh_size=0.4,
                     order=2, workdir=tempfile.mkdtemp(prefix="cap_"))
    except M.FeaError as exc:
        assert "网格过大" in str(exc)
        assert "上限" in str(exc)
    else:
        raise AssertionError("超预算网格应拒算")


@pytest.mark.skipif(not (has_bridge and has_brep), reason="缺 brep/gmsh/ccx")
def test_combined_cli_path_on_plate() -> None:
    """FEA（板悬臂）+ DFM（打印最小壁厚）合起来能跑，并给出 pass/weak。"""
    from acadkit.fea import brep_bridge as BB
    from acadkit.dfm.rules import check_print3d
    part = B.plate(length=200, width=100, thickness=8)
    fea = BB.cantilever_part(part, force=100, E=210000, nu=0.3, mesh_size=6.0,
                             axis="x", load_axis="z",
                             workdir=tempfile.mkdtemp(prefix="cmb_"))
    dfm = check_print3d(min_wall=8.0, overhang_deg=0.0, nozzle=0.4)
    loose = CB.combine(fea, sigma_allow=140, dfm=dfm, deflection_limit=0.5)
    tight = CB.combine(fea, sigma_allow=140, dfm=dfm, deflection_limit=0.1)
    assert loose.verdict == "pass", loose.to_text()
    assert tight.verdict == "weak", tight.to_text()


@pytest.mark.skipif(not (has_bridge and has_brep), reason="缺 brep/gmsh/ccx")
def test_sweep_plate_thickness_is_monotone() -> None:
    values = [8.0, 12.0]
    sw = SW.sweep(
        factory=lambda t: B.plate(length=200, width=100, thickness=t),
        param="thickness", values=values, case="cantilever", force=100,
        E=210000, nu=0.3, mesh_size=4.0, tol=5e-2,
        workdir=tempfile.mkdtemp(prefix="sw_"))
    assert len(sw.points) == 2
    assert all(p.ok for p in sw.points), sw.to_text()
    # 越厚越刚
    assert sw.points[0].measured > sw.points[1].measured
    # 应力随厚度下降（弯曲应力 ∝ 1/t²）
    assert sw.points[0].stress_nominal > sw.points[1].stress_nominal
    best = SW.pick_min(sw, max_stress=sw.points[1].stress_nominal)
    assert best == 12.0
