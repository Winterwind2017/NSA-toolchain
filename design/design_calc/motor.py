"""
电机选型计算

种类推荐、驱动功率、步进开环、伺服（惯量/转矩/RMS）。
公式来源: 鸣志/安川/三菱伺服选型手册、非标自动化设计经验、BV13t896UEWL P8 大纲
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServoResult:
    """伺服电机选型计算结果"""
    load_inertia: float = 0.0          # 负载折算惯量 kg·m²
    total_inertia: float = 0.0         # 总惯量 (含联轴器) kg·m²
    inertia_ratio: float = 0.0         # 惯量比 JL/JM
    max_speed_rpm: float = 0.0         # 所需最大转速 rpm
    friction_torque: float = 0.0       # 摩擦转矩 N·m
    accel_torque: float = 0.0          # 加速转矩 N·m
    total_accel_torque: float = 0.0    # 总加速转矩 N·m
    rms_torque: float = 0.0            # RMS 转矩 N·m
    required_power_kw: float = 0.0     # 所需功率 kW
    recommended_motor: str = ""        # 推荐电机规格
    warnings: list = field(default_factory=list)


def servo_selection(
    load_mass: float,
    lead: float = 10.0,
    max_speed: float = 500.0,
    accel_time: float = 0.1,
    decel_time: Optional[float] = None,
    constant_time: float = 0.5,
    friction_coeff: float = 0.02,
    efficiency: float = 0.9,
    motor_inertia: float = 0.0,
    coupling_inertia: float = 0.0,
    external_force: float = 0.0,
    safety_factor: float = 1.3,
) -> ServoResult:
    """
    伺服电机选型计算 (丝杆传动)

    Args:
        load_mass: 负载质量 kg
        lead: 丝杆导程 mm
        max_speed: 最大线速度 mm/s
        accel_time: 加速时间 s
        decel_time: 减速时间 s (默认=加速时间)
        constant_time: 匀速时间 s
        friction_coeff: 摩擦系数 (直线导轨 0.01~0.05)
        efficiency: 传动效率
        motor_inertia: 预选电机转子惯量 kg·m² (0=自动估算)
        coupling_inertia: 联轴器惯量 kg·m²
        external_force: 外力 N (如重力分量)
        safety_factor: 安全系数

    Returns:
        ServoResult 选型结果
    """
    r = ServoResult()
    decel_time = decel_time or accel_time

    lead_m = lead / 1000.0  # mm → m
    g = 9.81

    # 1. 负载折算惯量 (丝杆传动)
    r.load_inertia = load_mass * (lead_m / (2 * math.pi)) ** 2

    # 2. 总惯量
    if motor_inertia <= 0:
        motor_inertia = r.load_inertia * 0.5  # 初估
    r.total_inertia = r.load_inertia + coupling_inertia
    r.inertia_ratio = r.total_inertia / motor_inertia if motor_inertia > 0 else 999

    if r.inertia_ratio > 10:
        r.warnings.append(f"惯量比 {r.inertia_ratio:.1f} 过大(>10)，建议加减速机或换大惯量电机")
    elif r.inertia_ratio > 5:
        r.warnings.append(f"惯量比 {r.inertia_ratio:.1f} 偏大，高速定位可能振荡")

    # 3. 电机转速
    r.max_speed_rpm = max_speed * 60.0 / lead  # mm/s → rpm

    # 4. 摩擦转矩
    r.friction_torque = (friction_coeff * load_mass * g + external_force) * lead_m / (2 * math.pi * efficiency)

    # 5. 加速转矩
    omega_dot = 2 * math.pi * r.max_speed_rpm / (60 * accel_time)  # rad/s²
    r.accel_torque = (motor_inertia + r.total_inertia) * omega_dot

    # 6. 总加速转矩
    r.total_accel_torque = r.accel_torque + r.friction_torque

    # 7. RMS 转矩
    t_total = accel_time + constant_time + decel_time
    t_run = r.friction_torque
    t_dec = r.accel_torque - r.friction_torque  # 减速时摩擦帮助减速
    r.rms_torque = math.sqrt(
        (r.total_accel_torque**2 * accel_time + t_run**2 * constant_time + t_dec**2 * decel_time) / t_total
    )

    # 8. 所需功率
    r.required_power_kw = r.rms_torque * 2 * math.pi * r.max_speed_rpm / (60 * 1000) * safety_factor

    # 9. 推荐电机
    r.recommended_motor = _recommend_motor(r.rms_torque * safety_factor, r.total_accel_torque * safety_factor, r.max_speed_rpm)

    return r


def _recommend_motor(rms_torque: float, peak_torque: float, speed_rpm: float) -> str:
    """根据转矩和转速推荐电机规格"""
    # 常见伺服电机额定转矩表 (3000rpm)
    motors = [
        (0.1, 0.32, "100W"),
        (0.2, 0.64, "200W"),
        (0.4, 1.27, "400W"),
        (0.75, 2.39, "750W"),
        (1.0, 3.18, "1.0kW"),
        (1.5, 4.77, "1.5kW"),
        (2.0, 6.37, "2.0kW"),
        (3.0, 9.55, "3.0kW"),
        (5.0, 15.9, "5.0kW"),
    ]
    for power, torque, label in motors:
        if torque >= rms_torque:
            return f"{label} (额定转矩 {torque} N·m, 需 ≥ {rms_torque:.2f} N·m)"
    return f">5kW (需额定转矩 ≥ {rms_torque:.2f} N·m, 请查厂家样本)"


_STEPPER_FLANGES = [
    (28, 0.10, 1.3e-7),
    (42, 0.48, 5.4e-6),
    (57, 1.20, 2.8e-5),
    (86, 4.50, 1.4e-4),
]

_ASYNC_KW = [0.12, 0.18, 0.25, 0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0, 4.0, 5.5, 7.5, 11.0, 15.0]


def recommend_type(
    positioning: bool = True,
    continuous_duty: bool = False,
    repeatability_mm: float = 0.05,
    speed_rpm: float = 300.0,
    speed_mm_s: float = 0.0,
    load_kg: float = 5.0,
    cost_sensitive: bool = False,
    vertical: bool = False,
    no_backlash: bool = False,
) -> dict:
    """
    先定电机种类：异步 / 减速电机 / 步进 / 伺服 / 直驱。

    定位轴的惯量与 RMS 仍走 servo_selection；连转功率走 drive_power。
    """
    notes: list = []
    rpm = speed_rpm
    if speed_mm_s > 0:
        rpm = max(rpm, speed_mm_s * 6.0)  # 按 10 mm 导程估电机侧转速量级

    if vertical:
        notes.append("垂直轴必须抱闸或机械自锁，断电不能溜车")

    if continuous_duty and not positioning:
        motor = "三相异步+减速机" if rpm < 500 else "三相异步（变频可选）"
        reason = "连续运转不定位，优先寿命和效率"
        if rpm < 200:
            notes.append("出轴太慢时用减速机把电机拉到 1000~1500 rpm")
        return {"motor": motor, "reason": reason, "notes": notes, "next": "drive_power"}

    if no_backlash and positioning and repeatability_mm <= 0.02:
        motor = "DDR/DDL直驱"
        reason = "定位精度高且不能接受减速机/丝杆背隙"
        notes.append("安装面、电缆、冷却按厂家样本；预算不够改伺服+谐波/行星")
        return {"motor": motor, "reason": reason, "notes": notes, "next": "厂家直驱样本"}

    if not positioning:
        motor = "减速电机"
        reason = "间歇慢转、不要求走到精确位置"
        notes.append("若要重复停位，改伺服+减速机")
        return {"motor": motor, "reason": reason, "notes": notes, "next": "drive_power"}

    high_speed = rpm >= 800 or speed_mm_s >= 400
    precise = repeatability_mm <= 0.05
    light_slow = (not high_speed) and (not precise) and load_kg <= 10 and rpm < 400

    if cost_sensitive and light_slow:
        motor = "步进"
        reason = "低速轻载、精度可放到 0.1 mm 级、成本敏感"
        notes.append("按矩频曲线校核工作转速转矩，不要只用保持转矩")
        notes.append("加速过快或卡死会丢步且不开环报警")
        if vertical:
            notes.append("垂直步进优先改伺服+抱闸")
        if rpm >= 600:
            notes.append("电机轴 ≥600 rpm 时步进有效转矩下降，建议改伺服")
        return {"motor": motor, "reason": reason, "notes": notes, "next": "stepper_selection"}

    motor = "交流伺服"
    reason = "定位轴默认：闭环、可高速、可频繁加减速"
    if not precise and cost_sensitive:
        notes.append("精度不严仍建议伺服，避免开环丢步")
    if high_speed:
        notes.append("高速轴先匹配传动（带/齿条），再做惯量与 RMS")
    return {"motor": motor, "reason": reason, "notes": notes, "next": "servo_selection"}


def drive_power(
    torque_nm: float,
    rpm: float,
    efficiency: float = 0.8,
    safety: float = 2.0,
) -> dict:
    """
    驱动电机功率：P(kW) = T·n / 9550，再除以效率、乘安全系数。
    """
    if rpm <= 0:
        raise ValueError("rpm 必须 > 0")
    if efficiency <= 0:
        raise ValueError("efficiency 必须 > 0")

    p_mech = torque_nm * rpm / 9550.0
    p_need = p_mech / efficiency * safety
    selected = next((p for p in _ASYNC_KW if p >= p_need), None)
    warnings: list = []
    if safety >= 4:
        warnings.append("安全系数 ≥4 只适合冲击/惯量说不清的驱动轴，不要套到伺服定位")
    if rpm < 100:
        warnings.append("出轴转速过低，先加减速机再算电机功率")

    return {
        "mechanical_kw": round(p_mech, 3),
        "required_kw": round(p_need, 3),
        "selected_kw": selected if selected is not None else f">{_ASYNC_KW[-1]}",
        "torque_nm": torque_nm,
        "rpm": rpm,
        "efficiency": efficiency,
        "safety": safety,
        "warnings": warnings,
    }


def linear_power_w(
    force_n: float,
    speed_m_s: float,
    efficiency: float = 0.8,
    safety: float = 2.0,
) -> dict:
    """直线功率：P(W) = F·v，再计入效率与安全系数。"""
    if speed_m_s < 0:
        raise ValueError("speed_m_s 不能为负")
    p_mech = force_n * speed_m_s
    p_need = p_mech / efficiency * safety
    return {
        "mechanical_w": round(p_mech, 1),
        "required_w": round(p_need, 1),
        "required_kw": round(p_need / 1000.0, 3),
        "efficiency": efficiency,
        "safety": safety,
    }


def stepper_selection(
    load_mass: float,
    lead: float = 10.0,
    max_speed: float = 100.0,
    accel_time: float = 0.2,
    friction_coeff: float = 0.05,
    efficiency: float = 0.9,
    ratio: float = 1.0,
    safety_factor: float = 2.0,
    motor_inertia: float = 0.0,
    step_angle_deg: float = 1.8,
    microstep: float = 1.0,
    external_force: float = 0.0,
) -> dict:
    """
    步进电机选型（丝杆/同步带直线，开环）。

    输出的是工作转速下需要的转矩；保持转矩只作法兰初选，必须再对矩频曲线。
    """
    if ratio <= 0 or accel_time <= 0 or lead <= 0:
        raise ValueError("ratio / accel_time / lead 必须 > 0")

    lead_m = lead / 1000.0
    g = 9.81
    j_load = load_mass * (lead_m / (2 * math.pi)) ** 2
    n_load = max_speed * 60.0 / lead
    n_motor = n_load * ratio

    t_f = (friction_coeff * load_mass * g + external_force) * lead_m / (2 * math.pi * efficiency)
    t_f_motor = t_f / ratio

    if motor_inertia <= 0:
        motor_inertia = j_load / (ratio ** 2) * 0.2

    j_motor_side = motor_inertia + j_load / (ratio ** 2)
    omega_dot = 2 * math.pi * n_motor / (60.0 * accel_time)
    t_accel = j_motor_side * omega_dot
    t_need = safety_factor * (t_accel + t_f_motor) / efficiency

    inertia_ratio = (j_load / (ratio ** 2)) / motor_inertia if motor_inertia > 0 else 999
    steps_per_rev = 360.0 / step_angle_deg * microstep
    pulse_pps = n_motor / 60.0 * steps_per_rev

    flange = None
    for size, hold, _j in _STEPPER_FLANGES:
        if hold >= t_need:
            flange = f"{size} 机座 (保持转矩 {hold} N·m ≥ 需求 {t_need:.3f} N·m)"
            break
    if flange is None:
        flange = f">86 机座或加减速机 (需求 {t_need:.3f} N·m)，更建议改伺服"
    if n_motor >= 800:
        flange = f"电机 {n_motor:.0f} rpm，不推荐步进，改伺服（转矩需求 {t_need:.3f} N·m）"

    warnings: list = []
    if n_motor >= 600:
        warnings.append(f"电机转速 {n_motor:.0f} rpm，步进矩频下降，应按曲线校核或改伺服")
    if inertia_ratio > 10:
        warnings.append(f"惯量比 {inertia_ratio:.1f} >10，高速点位易丢步，加减速或改伺服")
    elif inertia_ratio > 5:
        warnings.append(f"惯量比 {inertia_ratio:.1f}，输送可接受，定位轴尽量压到 10 以内")
    warnings.append("保持转矩≠工作转矩，必须用矩频曲线对应 pps 的转矩校核")

    return {
        "load_inertia": j_load,
        "motor_rpm": round(n_motor, 1),
        "pulse_pps": round(pulse_pps, 1),
        "friction_torque_nm": round(t_f_motor, 4),
        "accel_torque_nm": round(t_accel, 4),
        "required_torque_nm": round(t_need, 4),
        "inertia_ratio": round(inertia_ratio, 2),
        "recommended_flange": flange,
        "warnings": warnings,
    }


def cylinder_selection(
    load_force: float,
    pressure: float = 0.5,
    load_rate: float = 0.5,
    speed: str = "medium",
) -> dict:
    """
    气缸缸径选型

    Args:
        load_force: 负载力 N
        pressure: 工作压力 MPa
        load_rate: 负载率 (静载0.7~0.8, 动载0.35~0.5)
        speed: 速度等级 'low'/'medium'/'high'

    Returns:
        dict 含推荐缸径、理论出力等
    """
    # 根据速度调整负载率
    speed_adj = {"low": 0.6, "medium": 0.45, "high": 0.3}
    beta = min(load_rate, speed_adj.get(speed, 0.45))

    # 理论出力
    F0 = load_force / beta

    # 缸径计算 D = sqrt(4*F0 / (pi*P))  单位: N, MPa → mm
    D_calc = math.sqrt(4 * F0 / (math.pi * pressure))  # mm (因为 MPa = N/mm²)

    # 标准缸径
    standard = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320]
    D_selected = next((d for d in standard if d >= D_calc), standard[-1])

    # 实际理论出力
    F0_actual = (math.pi / 4) * D_selected**2 * pressure

    return {
        "load_force_N": load_force,
        "load_rate": beta,
        "required_F0_N": F0,
        "calc_diameter_mm": round(D_calc, 1),
        "selected_diameter_mm": D_selected,
        "actual_F0_N": round(F0_actual, 1),
        "margin": round((F0_actual - load_force) / load_force * 100, 1),
    }


def ballscrew_life(
    Ca: float,
    Fm: float,
    fw: float = 1.2,
    nm: float = 1000.0,
) -> dict:
    """
    滚珠丝杆寿命计算

    Args:
        Ca: 额定动载荷 N
        Fm: 等效轴向载荷 N
        fw: 载荷系数 (平稳1.0~1.2, 一般1.2~1.5, 冲击1.5~2.0)
        nm: 平均转速 rpm

    Returns:
        dict 含寿命转数、小时数
    """
    L_rev = (Ca / (Fm * fw)) ** 3 * 1e6  # 转
    L_hours = L_rev / (60 * nm)
    L_km = L_rev * 0  # 需要导程才能算km

    return {
        "life_revolutions": round(L_rev),
        "life_hours": round(L_hours, 1),
        "life_years_8h": round(L_hours / (8 * 250), 2),
    }


def ballscrew_critical_speed(
    dr: float,
    L: float,
    fix_type: str = "fixed-supported",
) -> float:
    """
    丝杆临界转速

    Args:
        dr: 丝杆沟槽底径 mm
        L: 安装间距 mm
        fix_type: 'fixed-free'/'fixed-supported'/'fixed-fixed'

    Returns:
        临界转速 rpm
    """
    f_map = {"fixed-free": 3.4, "fixed-supported": 15.1, "fixed-fixed": 21.9}
    f = f_map.get(fix_type, 15.1)
    n_cr = f * (dr / L**2) * 1e7
    return round(n_cr, 0)


def tolerance_chain_extreme(rings: list) -> dict:
    """
    尺寸链极值法计算

    Args:
        rings: list of dict, 每个环 {"nominal": float, "upper": float, "lower": float, "type": "increasing"/"decreasing"}

    Returns:
        dict 封闭环结果
    """
    nom = 0.0
    es = 0.0
    ei = 0.0
    tol_sum = 0.0

    for ring in rings:
        t = ring["upper"] - ring["lower"]
        tol_sum += abs(t)
        if ring["type"] == "increasing":
            nom += ring["nominal"]
            es += ring["upper"]
            ei += ring["lower"]
        else:
            nom -= ring["nominal"]
            es -= ring["lower"]
            ei -= ring["upper"]

    return {
        "nominal": nom,
        "upper_deviation": round(es, 4),
        "lower_deviation": round(ei, 4),
        "tolerance": round(es - ei, 4),
        "max": round(nom + es, 4),
        "min": round(nom + ei, 4),
    }


def tolerance_chain_statistical(rings: list) -> dict:
    """
    尺寸链统计法计算 (概率法)

    Args:
        rings: 同极值法格式

    Returns:
        dict 封闭环结果
    """
    nom = 0.0
    tol_sq_sum = 0.0

    for ring in rings:
        t = ring["upper"] - ring["lower"]
        tol_sq_sum += t**2
        if ring["type"] == "increasing":
            nom += ring["nominal"]
        else:
            nom -= ring["nominal"]

    tol = math.sqrt(tol_sq_sum)
    half_tol = tol / 2

    return {
        "nominal": nom,
        "tolerance": round(tol, 4),
        "upper_deviation": round(half_tol, 4),
        "lower_deviation": round(-half_tol, 4),
        "max": round(nom + half_tol, 4),
        "min": round(nom - half_tol, 4),
    }


def von_mises(sigma_x: float, sigma_y: float, tau_xy: float) -> float:
    """von Mises 等效应力 (平面应力)"""
    return math.sqrt(sigma_x**2 - sigma_x * sigma_y + sigma_y**2 + 3 * tau_xy**2)


def beam_deflection_cantilever(F: float, L: float, E: float, I: float) -> float:
    """悬臂梁端部集中力挠度"""
    return F * L**3 / (3 * E * I)


def beam_deflection_simple(F: float, L: float, E: float, I: float) -> float:
    """简支梁中点集中力挠度"""
    return F * L**3 / (48 * E * I)


def euler_buckling(E: float, I: float, L: float, K: float = 1.0) -> float:
    """欧拉临界载荷"""
    return math.pi**2 * E * I / (K * L)**2
