"""
气缸选型计算

公式来源: SMC/亚德客气缸选型手册、米思米技术指南
"""

import math
from typing import Optional


# 标准缸径系列 (mm)
STANDARD_BORES = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320]

# 负载率推荐值
LOAD_RATE_TABLE = {
    "static": 0.75,       # 静负载 (夹紧)
    "slow": 0.60,         # <100 mm/s
    "medium": 0.45,       # 100~500 mm/s
    "fast": 0.30,         # >500 mm/s
}


def select_bore(
    load_force: float,
    pressure: float = 0.5,
    speed_class: str = "medium",
    load_rate_override: Optional[float] = None,
    action: str = "double",
) -> dict:
    """
    根据负载力选择气缸缸径

    Args:
        load_force: 负载力 N
        pressure: 工作压力 MPa (常用 0.4~0.6)
        speed_class: 'static'/'slow'/'medium'/'fast'
        load_rate_override: 手动指定负载率 (覆盖 speed_class)
        action: 'double' 双作用 / 'single' 单作用

    Returns:
        dict 选型结果
    """
    beta = load_rate_override or LOAD_RATE_TABLE.get(speed_class, 0.45)

    # 理论出力 F0 = F_load / beta
    F0_required = load_force / beta

    # 缸径计算: F0 = (π/4)·D²·P  →  D = √(4·F0 / (π·P))
    # 单位: F0[N], P[MPa=N/mm²] → D[mm]
    D_calc = math.sqrt(4 * F0_required / (math.pi * pressure))

    # 圆整到标准缸径
    D_selected = next((d for d in STANDARD_BORES if d >= D_calc), STANDARD_BORES[-1])

    # 实际理论出力
    if action == "double":
        F0_actual = (math.pi / 4) * D_selected**2 * pressure
        # 拉力 (活塞杆 d ≈ 0.3D)
        d_rod = 0.3 * D_selected
        F0_pull = (math.pi / 4) * (D_selected**2 - d_rod**2) * pressure
    else:
        F0_actual = (math.pi / 4) * D_selected**2 * pressure * 0.85  # 单作用效率低
        F0_pull = 0

    margin_push = (F0_actual * beta - load_force) / load_force * 100

    result = {
        "load_force_N": load_force,
        "pressure_MPa": pressure,
        "load_rate": beta,
        "speed_class": speed_class,
        "required_F0_N": round(F0_required, 1),
        "calc_diameter_mm": round(D_calc, 1),
        "selected_bore_mm": D_selected,
        "push_force_N": round(F0_actual, 1),
        "pull_force_N": round(F0_pull, 1),
        "actual_output_N": round(F0_actual * beta, 1),
        "margin_percent": round(margin_push, 1),
        "action": action,
    }

    if margin_push < 10:
        result["warning"] = f"余量仅 {margin_push:.0f}%，建议选大一号缸径"

    return result


def select_stroke(
    required_stroke: float,
    application: str = "general",
) -> dict:
    """
    行程选择

    Args:
        required_stroke: 计算所需行程 mm
        application: 'general' 一般 / 'clamp' 夹紧

    Returns:
        dict 推荐行程
    """
    if application == "clamp":
        margin = 15  # 夹紧加 10~20mm
    else:
        margin = 2   # 一般加 1~2mm

    total = required_stroke + margin

    # 标准行程系列
    standard_strokes = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500]
    selected = next((s for s in standard_strokes if s >= total), total)

    return {
        "required_mm": required_stroke,
        "margin_mm": margin,
        "total_mm": total,
        "selected_stroke_mm": selected,
        "application": application,
    }


def check_lateral_load(
    bore: float,
    pressure: float,
    lateral_force: float,
) -> dict:
    """
    横向载荷校核

    允许横向载荷 ≈ 最大推力的 1/20

    Args:
        bore: 缸径 mm
        pressure: 工作压力 MPa
        lateral_force: 横向载荷 N

    Returns:
        dict 校核结果
    """
    max_thrust = (math.pi / 4) * bore**2 * pressure
    allowed_lateral = max_thrust / 20

    return {
        "max_thrust_N": round(max_thrust, 1),
        "allowed_lateral_N": round(allowed_lateral, 1),
        "actual_lateral_N": lateral_force,
        "pass": lateral_force <= allowed_lateral,
        "recommendation": "OK" if lateral_force <= allowed_lateral else "需改用带导杆气缸或加外部导轨",
    }


def buffer_selection(
    speed: float,
    bore: float,
    load_mass: float,
) -> dict:
    """
    缓冲方式选择

    Args:
        speed: 缸速 mm/s
        bore: 缸径 mm
        load_mass: 运动部件质量 kg

    Returns:
        dict 推荐缓冲方式
    """
    kinetic_energy = 0.5 * load_mass * (speed / 1000.0)**2  # J

    if speed < 100:
        buffer_type = "无缓冲"
    elif speed < 300:
        buffer_type = "橡胶缓冲"
    elif speed < 500:
        buffer_type = "气缓冲"
    else:
        buffer_type = "液压缓冲器"

    return {
        "speed_mm_s": speed,
        "kinetic_energy_J": round(kinetic_energy, 3),
        "recommended_buffer": buffer_type,
    }
