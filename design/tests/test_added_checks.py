"""驱动复核、渐开线坐标、交付门禁。数字在测试里另算一遍。"""

from __future__ import annotations

import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from design_calc import ballscrew, drive_audit, gear  # noqa: E402
import delivery_gate  # noqa: E402


_MOTOR = dict(
    motor_peak_nm=2.0,
    motor_rated_nm=1.0,
    motor_max_rpm=3000.0,
    rotor_inertia_kgm2=1e-4,
)


def _horizontal(**extra):
    args = dict(
        mass_kg=10.0,
        distance_mm=200.0,
        max_speed_mm_s=100.0,
        accel_mm_s2=1000.0,
        transmission="screw",
        lead_mm=10.0,
        efficiency=1.0,
        incline_deg=0.0,
        friction=0.0,
    )
    args.update(_MOTOR)
    args.update(extra)
    return drive_audit.audit_linear_drive(**args)


def test_horizontal_screw_peak_and_rms():
    k = 0.01 / (2.0 * math.pi)
    alpha = 1.0 / k
    j_load = 10.0 * k * k
    peak = j_load * alpha + 1e-4 * alpha
    report = _horizontal()
    assert abs(report["reads"]["peak_nm"] - peak) < 1e-6
    t_acc, t_cruise = 0.1, 1.9
    rms = math.sqrt(2.0 * peak * peak * t_acc / (2.0 * t_acc + t_cruise))
    assert abs(report["reads"]["rms_nm"] - rms) < 1e-6
    assert report["reads"]["motor_rpm"] == 600.0
    assert report["ok"] is True
    assert report["review_required"] is True


def test_belt_matches_screw_when_radius_is_lead_over_2pi():
    radius = 10.0 / (2.0 * math.pi)
    screw = _horizontal()
    belt = _horizontal(transmission="belt", lead_mm=None, pulley_radius_mm=radius)
    assert abs(screw["reads"]["peak_nm"] - belt["reads"]["peak_nm"]) < 1e-9
    assert abs(screw["reads"]["rms_nm"] - belt["reads"]["rms_nm"]) < 1e-9


def test_short_move_is_triangle_and_vertical_needs_brake():
    short = _horizontal(distance_mm=5.0)
    assert abs(short["reads"]["v_peak_m_s"] - math.sqrt(0.005)) < 1e-6
    assert short["reads"]["t_cruise_s"] == 0.0

    vertical = _horizontal(incline_deg=90.0, has_brake=False)
    brake = next(item for item in vertical["checks"] if item["check"] == "brake")
    assert brake["ok"] is False
    assert vertical["ok"] is False
    held = _horizontal(incline_deg=90.0, has_brake=True)
    assert next(item for item in held["checks"] if item["check"] == "brake")["ok"] is True


def test_critical_speed_uses_ballscrew_formula():
    fast = _horizontal(
        max_speed_mm_s=1000.0,
        distance_mm=2000.0,
        screw_diameter_mm=12.0,
        screw_length_mm=800.0,
        motor_max_rpm=20000.0,
    )
    limit = 0.8 * ballscrew.critical_speed(12.0, 800.0)
    check = next(item for item in fast["checks"] if item["check"] == "critical_speed")
    assert check["want"] == limit
    assert check["got"] > limit
    assert check["ok"] is False


def test_involute_hits_base_and_pitch_circle():
    rb = gear.base_radius_mm(2.0, 30, 20.0)
    assert abs(rb - 30.0 * math.cos(math.radians(20.0))) < 1e-9
    base = gear.involute_xy(rb, 0.0)
    assert abs(math.hypot(*base) - rb) < 1e-9
    roll = gear.pitch_roll(20.0)
    pitch = gear.involute_xy(rb, roll)
    assert abs(math.hypot(*pitch) - 30.0) < 1e-9


def test_delivery_gate_rejects_old_and_accepts_new(tmp_path):
    path = tmp_path / "part.step"
    path.write_bytes(b"ISO-10303-21;\nold")
    old = time.time() + 5
    os.utime(path, (old - 100, old - 100))
    stale = delivery_gate.accept_new_file(str(path), old, kind="step")
    assert stale["ok"] is False

    started = time.time()
    time.sleep(0.02)
    path.write_bytes(b"ISO-10303-21;\nnew-body-with-enough-bytes")
    fresh = delivery_gate.accept_new_file(str(path), started, kind="step")
    assert fresh["ok"] is True

    previous = delivery_gate.content_changed(str(path), "0" * 64)
    assert previous["ok"] is True
    same = delivery_gate.content_changed(str(path), previous["checks"][0]["got"])
    assert same["ok"] is False
