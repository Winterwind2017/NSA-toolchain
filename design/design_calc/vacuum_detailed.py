"""
真空系统详细设计

真空发生器、真空吸盘、真空罐详细设计计算。
公式来源: SMC/施迈茨选型手册
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class VacuumGeneratorResult:
    """真空发生器选型结果"""
    suction_flow_l_min: float = 0.0     # 吸入流量 L/min
    vacuum_kpa: float = -60.0           # 真空度 kPa
    consumption_flow_l_min: float = 0.0 # 耗气量 L/min
    recommended_model: str = ""
    warnings: List[str] = field(default_factory=list)


def vacuum_generator_selection(
    payload_kg: float,
    cup_diameter_mm: float,
    number_of_cups: int = 1,
    cycle_time_s: float = 2.0,
) -> VacuumGeneratorResult:
    """
    真空发生器详细选型
    
    Args:
        payload_kg: 负载重量 kg
        cup_diameter_mm: 吸盘直径 mm
        number_of_cups: 吸盘数量
        cycle_time_s: 循环时间 s
    
    Returns:
        VacuumGeneratorResult
    """
    result = VacuumGeneratorResult()
    
    g = 9.81
    
    # 单吸盘吸力
    cup_area = math.pi * (cup_diameter_mm / 2000)**2  # m²
    single_force = abs(result.vacuum_kpa) * 1000 * cup_area  # N
    
    # 总吸力
    total_force = single_force * number_of_cups
    
    # 安全系数校核
    required_force = payload_kg * g * 3.0
    if total_force < required_force:
        result.warnings.append(
            f"吸力不足: {total_force:.1f} N < 需要 {required_force:.1f} N"
        )
    
    # 吸入流量计算
    # 每个吸盘容积 + 管路容积
    cup_volume = cup_area * 0.01 * 1000  # L (假设吸附深度10mm)
    total_volume = cup_volume * number_of_cups * 2.0  # 2倍管路余量
    
    # 吸入流量
    suction_flow = total_volume / cycle_time_s * 60
    result.suction_flow_l_min = suction_flow
    
    # 耗气量 (真空发生器通常是吸入流量的 3-5 倍)
    result.consumption_flow_l_min = suction_flow * 4
    
    # 推荐型号
    if suction_flow < 5:
        result.recommended_model = "SMC ZH10DSA"
    elif suction_flow < 15:
        result.recommended_model = "SMC ZH13DSA"
    elif suction_flow < 30:
        result.recommended_model = "SMC ZH15DSA"
    elif suction_flow < 60:
        result.recommended_model = "SMC ZH18DSA"
    else:
        result.recommended_model = "真空泵"
        result.warnings.append("流量较大，建议选用真空泵")
    
    return result


@dataclass
class VacuumTankResult:
    """真空罐计算结果"""
    tank_volume_l: float = 0.0          # 罐容积 L
    hold_time_s: float = 0.0           # 保压时间 s
    recommended_size: str = ""
    warnings: List[str] = field(default_factory=list)


def vacuum_tank_calculation(
    leakage_rate_l_min: float,
    hold_time_s: float = 3.0,
    allowable_pressure_drop: float = 5.0,
) -> VacuumTankResult:
    """
    真空罐容积计算
    
    Args:
        leakage_rate_l_min: 泄漏率 L/min
        hold_time_s: 需要保压时间 s
        allowable_pressure_drop: 允许压力降 kPa
    
    Returns:
        VacuumTankResult
    """
    result = VacuumTankResult()
    result.hold_time_s = hold_time_s
    
    # 真空罐容积计算
    # V = Q * t / ΔP * P_atm
    # 简化公式
    tank_volume = leakage_rate_l_min * (hold_time_s / 60) * 100 / allowable_pressure_drop
    result.tank_volume_l = tank_volume
    
    # 推荐规格
    standard_tanks = [0.5, 1, 2, 5, 10, 20, 50]
    for size in standard_tanks:
        if size >= tank_volume:
            result.recommended_size = f"{size}L"
            break
    
    return result
