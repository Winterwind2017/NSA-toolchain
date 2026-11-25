"""
滚珠丝杆与直线导轨选型计算

公式来源: THK/HIWIN/米思米选型手册、GB/T 17587
"""

import math
from typing import Optional


# 丝杆精度等级 (300mm 行程变动量 μm)
ACCURACY_GRADES = {
    "C0": 1.5, "C1": 2.5, "C2": 3.5, "C3": 5.0,
    "C5": 18, "C7": 50, "C10": 210,
}

# 安装方式系数
FIX_COEFFICIENTS = {
    "fixed-free": 3.4,
    "fixed-supported": 15.1,
    "fixed-fixed": 21.9,
    "fixed-fixed-preload": 21.9,
}


def select_lead(max_speed: float, motor_rpm: float, gear_ratio: float = 1.0) -> float:
    """
    计算丝杆导程

    Args:
        max_speed: 最大线速度 mm/s
        motor_rpm: 电机额定转速 rpm
        gear_ratio: 传动比 (直连=1)

    Returns:
        导程 mm
    """
    lead = max_speed * 60.0 / (motor_rpm * gear_ratio)
    # 圆整到标准导程
    standard_leads = [1, 2, 2.5, 3, 4, 5, 10, 16, 20, 25, 32, 40, 50]
    selected = next((l for l in standard_leads if l >= lead), lead)
    return selected


def select_accuracy(positioning_accuracy: float, stroke: float) -> str:
    """
    根据定位精度选择丝杆精度等级

    Args:
        positioning_accuracy: 单方向定位精度 mm
        stroke: 工作行程 mm

    Returns:
        推荐精度等级
    """
    # 换算到 300mm 的允许误差
    allowed_per_300 = positioning_accuracy * 300.0 / stroke if stroke > 0 else positioning_accuracy
    allowed_um = allowed_per_300 * 1000  # mm → μm

    for grade in ["C0", "C1", "C2", "C3", "C5", "C7", "C10"]:
        if ACCURACY_GRADES[grade] <= allowed_um:
            return grade
    return "C10"


def life_hours(Ca: float, Fm: float, fw: float, nm: float) -> dict:
    """
    丝杆疲劳寿命

    Args:
        Ca: 额定动载荷 N
        Fm: 等效轴向载荷 N
        fw: 载荷系数
        nm: 平均转速 rpm

    Returns:
        dict 寿命结果
    """
    L_rev = (Ca / (Fm * fw)) ** 3 * 1e6
    L_h = L_rev / (60 * nm)

    return {
        "life_revolutions": int(L_rev),
        "life_hours": round(L_h, 1),
        "life_years_2shift": round(L_h / (16 * 250), 2),
    }


def critical_speed(dr: float, L: float, fix_type: str = "fixed-supported") -> float:
    """
    丝杆临界转速

    Args:
        dr: 沟槽底径 mm
        L: 安装间距 mm
        fix_type: 安装方式

    Returns:
        临界转速 rpm
    """
    f = FIX_COEFFICIENTS.get(fix_type, 15.1)
    n_cr = f * (dr / L**2) * 1e7
    return round(n_cr, 0)


def dn_value(D: float, n: float) -> float:
    """
    DN 值校核

    Args:
        D: 丝杆公称直径 mm
        n: 转速 rpm

    Returns:
        DN 值
    """
    return D * n


def axial_load(mass: float, accel: float, friction: float, g: float = 9.81) -> dict:
    """
    各工况轴向载荷

    Args:
        mass: 负载质量 kg
        accel: 加速度 m/s²
        friction: 摩擦系数
        g: 重力加速度

    Returns:
        dict 各阶段载荷
    """
    F_friction = friction * mass * g
    F_accel = mass * accel

    return {
        "constant_N": round(F_friction, 1),
        "accel_N": round(F_accel + F_friction, 1),
        "decel_N": round(F_accel - F_friction, 1),
    }


def equivalent_load(Pa: float, ta: float, Pb: float, tb: float, Pc: float, tc: float) -> tuple:
    """
    等效轴向载荷和平均转速

    Args:
        Pa, ta: 加速阶段载荷 N 和时间 s
        Pb, tb: 匀速阶段载荷 N 和时间 s
        Pc, tc: 减速阶段载荷 N 和时间 s

    Returns:
        (Pm, 各阶段时间比)
    """
    t_total = ta + tb + tc
    if t_total == 0:
        return 0, {}

    # 立方平均
    Pm = ((Pa**3 * ta + Pb**3 * tb + abs(Pc)**3 * tc) / t_total) ** (1/3)

    ratios = {"accel": ta / t_total, "constant": tb / t_total, "decel": tc / t_total}
    return round(Pm, 1), ratios


# ─── 直线导轨 ────────────────────────────────────────────────

def guide_life_ball(C: float, P: float, fw: float = 1.2) -> float:
    """球型导轨寿命 (km)"""
    return (C / (fw * P)) ** 3 * 50


def guide_life_roller(C: float, P: float, fw: float = 1.2) -> float:
    """滚子型导轨寿命 (km)"""
    return (C / (fw * P)) ** (10/3) * 50


def guide_life_hours(L_km: float, stroke_mm: float, cycles_per_min: float) -> float:
    """导轨寿命 (小时)"""
    if stroke_mm == 0 or cycles_per_min == 0:
        return float('inf')
    return L_km * 1e6 / (2 * stroke_mm * cycles_per_min * 60)


def guide_static_safety(C0: float, P0: float) -> float:
    """静安全系数"""
    return C0 / P0 if P0 > 0 else float('inf')
