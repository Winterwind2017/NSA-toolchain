"""设计计算库的核心公式。不依赖 CAD。"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_calc import (  # noqa: E402
    ballscrew,
    cycle_time,
    cylinder,
    motor,
    strength,
    tolerance,
)


def test_packages_import():
    import design_calc

    for name in design_calc.__all__:
        assert hasattr(design_calc, name)


def test_servo_load_inertia():
    result = motor.servo_selection(load_mass=50, lead=10, max_speed=500)
    lead_m = 0.01
    expect = 50 * (lead_m / (2 * math.pi)) ** 2
    assert result.load_inertia == expect


def test_cylinder_bore_rounds_up():
    result = cylinder.select_bore(load_force=500, pressure=0.5, speed_class="medium")
    # F0 = 500 / 0.45，D = sqrt(4 F0 / (pi P)) ≈ 53.2 mm → 63
    assert result["load_rate"] == 0.45
    assert 53 < result["calc_diameter_mm"] < 54
    assert result["selected_bore_mm"] == 63
    assert result["margin_percent"] > 0


def test_ballscrew_life_cubic():
    life = ballscrew.life_hours(Ca=12000, Fm=2000, fw=1.2, nm=1500)
    revolutions = (12000 / (2000 * 1.2)) ** 3 * 1e6
    assert life["life_revolutions"] == int(revolutions)
    assert life["life_hours"] == round(revolutions / (60 * 1500), 1)


def test_cycle_time_parallel_group_is_not_summed():
    path = cycle_time.from_steps([
        {"name": "挡停", "time": 0.2},
        {"name": "夹紧", "time": 0.25, "group": "hold"},
        {"name": "定位", "time": 0.18, "group": "hold"},
        {"name": "喷码", "time": 0.4},
    ])
    assert path["critical_path_s"] == 0.85
    hold = path["steps"][1]
    assert hold["mode"] == "parallel"
    assert hold["time_s"] == 0.25

    ct = cycle_time.cycle_time(path["critical_path_s"], reset_s=0.15, margin=1.2)
    assert ct["cycle_time_s"] == round((0.85 + 0.15) * 1.2, 4)
    verdict = cycle_time.meets_target(ct["cycle_time_s"], target_s=2.0)
    assert verdict["ok"] is True


def test_goodman_and_tolerance_chain():
    n = strength.goodman_safety(sa=80, sm=50, Se=200, Sut=600)
    assert n == 1 / (80 / 200 + 50 / 600)

    chain = tolerance.tolerance_chain_extreme([
        {"nominal": 50, "upper": 0.02, "lower": 0, "type": "inc"},
        {"nominal": 30, "upper": 0.01, "lower": -0.01, "type": "dec"},
    ])
    assert chain["nominal"] == 20
    assert chain["upper"] == 0.03
    assert chain["lower"] == -0.01
