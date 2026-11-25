"""
直线驱动复核：丝杠或皮带，对照一台已经选定的电机。

这是方案校核，不是订货计算。反向效率、丝杠自锁和转矩-转速曲线没有建模型，
所以数值通过仍然要人看样本。缺电机数据时对应项失败，不当成通过。
"""

from __future__ import annotations

import math

from . import ballscrew

G = 9.81
_STEEP_DEG = 5.0


def _motion(distance_m: float, vmax: float, accel: float):
    """对称加减速。行程不够时退成三角，返回 (t_acc, t_cruise, v_peak)。"""
    if distance_m <= 0 or vmax <= 0 or accel <= 0:
        raise ValueError("行程、速度、加速度必须大于 0")
    reach = vmax * vmax / accel
    if distance_m <= reach:
        v_peak = math.sqrt(accel * distance_m)
        return v_peak / accel, 0.0, v_peak
    return vmax / accel, (distance_m - reach) / vmax, vmax


def _check(name: str, got, want, ok: bool) -> dict:
    return {"check": name, "got": got, "want": want, "ok": bool(ok)}


def audit_linear_drive(
    mass_kg: float,
    distance_mm: float,
    max_speed_mm_s: float,
    accel_mm_s2: float,
    transmission: str,
    motor_peak_nm: float,
    motor_rated_nm: float,
    motor_max_rpm: float,
    rotor_inertia_kgm2: float,
    lead_mm: float | None = None,
    pulley_radius_mm: float | None = None,
    incline_deg: float = 0.0,
    friction: float = 0.0,
    external_force_n: float = 0.0,
    return_external_force_n: float = 0.0,
    efficiency: float = 0.9,
    gear_ratio: float = 1.0,
    gear_efficiency: float = 1.0,
    screw_diameter_mm: float | None = None,
    screw_length_mm: float | None = None,
    dwell_s: float = 0.0,
    round_trip: bool = False,
    has_brake: bool = False,
    peak_safety: float = 1.5,
    rms_utilization: float = 0.8,
    density_kg_m3: float = 7800.0,
) -> dict:
    """
    复核峰值转矩、RMS、转速、惯量比；斜轴还要抱闸；丝杠给了直径和长度就核临界转速。

    倾角 0 为水平，正值表示去程向上。静力里不含 m·a，惯性只走 J·α。
    摩擦始终与运动反向。减速段的负转矩是回馈，峰值取绝对值，RMS 用平方。
    """
    errors: list[str] = []
    warnings = [
        "反向驱动效率和转矩-转速曲线没有建模，数值通过不等于可以下单",
    ]
    kind = (transmission or "").strip().lower()
    if kind not in ("screw", "belt"):
        raise ValueError("transmission 只能是 screw 或 belt")
    if mass_kg < 0 or friction < 0 or dwell_s < 0:
        raise ValueError("质量、摩擦、停留时间不能为负")
    if not 0 < efficiency <= 1 or not 0 < gear_efficiency <= 1:
        raise ValueError("效率必须在 (0, 1]")
    if gear_ratio <= 0 or peak_safety < 1 or not 0 < rms_utilization <= 1:
        raise ValueError("减速比、峰值安全系数或 RMS 利用率不合法")
    if rotor_inertia_kgm2 <= 0:
        errors.append("没有转子惯量，惯量比无法判断")

    if kind == "screw":
        if lead_mm is None or lead_mm <= 0:
            raise ValueError("丝杠必须给 lead_mm")
        k = (lead_mm / 1000.0) / (2.0 * math.pi)
    else:
        if pulley_radius_mm is None or pulley_radius_mm <= 0:
            raise ValueError("皮带必须给 pulley_radius_mm")
        k = pulley_radius_mm / 1000.0

    distance_m = distance_mm / 1000.0
    vmax = max_speed_mm_s / 1000.0
    accel = accel_mm_s2 / 1000.0
    t_acc, t_cruise, v_peak = _motion(distance_m, vmax, accel)
    alpha = accel / k
    j_load = mass_kg * k * k
    j_screw = 0.0
    if kind == "screw" and screw_diameter_mm and screw_length_mm:
        d = screw_diameter_mm / 1000.0
        length = screw_length_mm / 1000.0
        j_screw = density_kg_m3 * math.pi * length * d ** 4 / 32.0

    theta = math.radians(incline_deg)
    gravity = mass_kg * G * math.sin(theta)
    friction_n = friction * mass_kg * G * abs(math.cos(theta))

    def torque(force_n: float, alpha_axis: float) -> float:
        load = force_n * k + (j_load + j_screw) * alpha_axis
        reflected = load / (efficiency * gear_ratio * gear_efficiency)
        return reflected + rotor_inertia_kgm2 * alpha_axis * gear_ratio

    def stroke(force_n: float) -> list[tuple[float, float]]:
        segments = [
            (t_acc, torque(force_n, alpha)),
            (t_cruise, torque(force_n, 0.0)),
            (t_acc, torque(force_n, -alpha)),
        ]
        return [(t, tq) for t, tq in segments if t > 0]

    steep = abs(incline_deg) >= _STEEP_DEG
    segments = stroke(gravity + friction_n + external_force_n)
    if round_trip:
        segments += stroke(-gravity + friction_n + return_external_force_n)
    if dwell_s > 0:
        hold = 0.0 if has_brake or not steep else torque(gravity, 0.0)
        segments.append((dwell_s, hold))

    total_t = sum(t for t, _ in segments)
    if total_t <= 0:
        raise ValueError("运动时间合计为 0")
    peak = max(abs(tq) for _, tq in segments)
    mean_sq = sum(tq * tq * t for t, tq in segments) / total_t
    rms = math.sqrt(mean_sq)
    omega = v_peak / k
    rpm = omega * 60.0 / (2.0 * math.pi) * gear_ratio
    ratio = (j_load + j_screw) / (gear_ratio ** 2) / rotor_inertia_kgm2 if rotor_inertia_kgm2 > 0 else None
    if ratio is not None and ratio > 5:
        warnings.append("惯量比 %.1f 大于 5，先确认厂家允许值" % ratio)

    allowable_peak = motor_peak_nm / peak_safety
    allowable_rms = motor_rated_nm * rms_utilization
    checks = [
        _check("peak_torque", round(peak, 6), round(allowable_peak, 6), peak <= allowable_peak),
        _check("rms_torque", round(rms, 6), round(allowable_rms, 6), rms <= allowable_rms),
        _check("max_speed", round(rpm, 3), motor_max_rpm, rpm <= motor_max_rpm),
        _check(
            "inertia_ratio",
            None if ratio is None else round(ratio, 3),
            10.0,
            ratio is not None and ratio <= 10.0,
        ),
        _check("brake", bool(has_brake), steep, (not steep) or bool(has_brake)),
    ]
    if kind == "screw" and screw_diameter_mm and screw_length_mm:
        n_cr = ballscrew.critical_speed(screw_diameter_mm, screw_length_mm)
        limit = 0.8 * n_cr
        checks.append(_check("critical_speed", round(rpm / gear_ratio, 3), limit, rpm / gear_ratio <= limit))

    ok = not errors and all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "review_required": True,
        "transmission": kind,
        "reads": {
            "peak_nm": round(peak, 6),
            "rms_nm": round(rms, 6),
            "motor_rpm": round(rpm, 3),
            "v_peak_m_s": round(v_peak, 6),
            "inertia_ratio": None if ratio is None else round(ratio, 3),
            "t_acc_s": round(t_acc, 6),
            "t_cruise_s": round(t_cruise, 6),
        },
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
