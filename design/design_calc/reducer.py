"""
减速机选型计算

公式来源: 恩坦斯特/哈默纳科/纳博特斯克选型手册
"""

import math
from typing import Optional


# 减速机类型参数
REDUCER_TYPES = {
    "planetary": {"efficiency": 0.96, "backlash_arcmin": (1, 10), "ratio_range": (3, 100)},
    "harmonic": {"efficiency": 0.85, "backlash_arcmin": (0, 1), "ratio_range": (30, 160)},
    "rv": {"efficiency": 0.88, "backlash_arcmin": (1, 2), "ratio_range": (30, 200)},
    "worm": {"efficiency": 0.70, "backlash_arcmin": (10, 30), "ratio_range": (5, 100)},
    "helical": {"efficiency": 0.96, "backlash_arcmin": (5, 15), "ratio_range": (3, 200)},
}


def select_ratio(motor_rpm: float, output_rpm: float) -> float:
    """计算传动比"""
    return motor_rpm / output_rpm if output_rpm > 0 else 1.0


def output_torque(motor_torque: float, ratio: float,
                  efficiency: float = 0.96, ka: float = 1.3) -> float:
    """
    减速机输出扭矩

    Args:
        motor_torque: 电机扭矩 N·m
        ratio: 传动比
        efficiency: 传动效率
        ka: 工况系数 (平稳1.2~1.5, 冲击1.5~2.5)

    Returns:
        所需额定输出扭矩 N·m
    """
    return motor_torque * ratio * efficiency * ka


def reflected_inertia(load_inertia: float, ratio: float) -> float:
    """负载惯量折算到电机轴"""
    return load_inertia / (ratio ** 2)


def check_reducer(
    motor_torque: float,
    ratio: float,
    reducer_rated_torque: float,
    efficiency: float = 0.96,
    ka: float = 1.3,
) -> dict:
    """
    减速机校核

    Returns:
        dict 含校核结果
    """
    required = output_torque(motor_torque, ratio, efficiency, ka)
    margin = (reducer_rated_torque - required) / required * 100

    return {
        "required_torque_Nm": round(required, 2),
        "rated_torque_Nm": reducer_rated_torque,
        "margin_percent": round(margin, 1),
        "pass": reducer_rated_torque >= required,
    }


def recommend_type(
    load_kg: float,
    precision_arcmin: float,
    space_limited: bool = False,
    high_shock: bool = False,
) -> str:
    """
    推荐减速机类型

    Args:
        load_kg: 负载质量 kg
        precision_arcmin: 背隙要求 arcmin
        space_limited: 空间是否受限
        high_shock: 是否有高频冲击

    Returns:
        推荐类型
    """
    if precision_arcmin <= 1 and load_kg < 10:
        return "harmonic (谐波减速机: 零背隙/轻载/紧凑)"
    if load_kg > 10 or high_shock:
        return "rv (RV减速机: 高刚性/重载/抗冲击)"
    if precision_arcmin <= 3:
        return "planetary (行星减速机: 低背隙/通用精密)"
    if space_limited:
        return "harmonic (谐波减速机: 紧凑)"
    return "planetary (行星减速机: 性价比最优)"
