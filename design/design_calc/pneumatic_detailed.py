"""
气动系统详细计算

气缸速度、气管管径、真空系统详细计算。
公式来源: SMC/费斯托选型手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class CylinderSpeedResult:
    """气缸速度计算结果"""
    bore_dia_mm: float = 0.0            # 缸径 mm
    stroke_mm: float = 0.0              # 行程 mm
    pressure_mpa: float = 0.0           # 气压 MPa
    flow_l_min: float = 0.0             # 耗气量 L/min
    speed_mm_s: float = 0.0             # 速度 mm/s
    time_s: float = 0.0                  # 动作时间 s
    warnings: List[str] = field(default_factory=list)


def cylinder_speed_calculation(
    bore_dia_mm: float,
    stroke_mm: float,
    pressure_mpa: float = 0.5,
    flow_l_min: float = 100.0,
) -> CylinderSpeedResult:
    """
    气缸速度计算
    
    Args:
        bore_dia_mm: 缸径 mm
        stroke_mm: 行程 mm
        pressure_mpa: 工作气压 MPa
        flow_l_min: 气源流量 L/min
    
    Returns:
        CylinderSpeedResult
    """
    result = CylinderSpeedResult()
    result.bore_dia_mm = bore_dia_mm
    result.stroke_mm = stroke_mm
    result.pressure_mpa = pressure_mpa
    result.flow_l_min = flow_l_min
    
    d = bore_dia_mm
    L = stroke_mm
    
    # 气缸截面积
    A = math.pi * d**2 / 4  # mm²
    
    # 单行程耗气量 (L)
    # V = A * L / 1000 转换为 L
    volume_per_stroke = A * L / 1000  # cm³
    
    # 假设每分钟动作次数 (简化)
    cycles_per_min = flow_l_min / volume_per_stroke
    
    # 速度计算
    # v = L / t, t = 1/cycles_per_min (分钟)
    time_min = 1 / cycles_per_min if cycles_per_min > 0 else 0
    result.time_s = time_min * 60
    result.speed_mm_s = L / result.time_s if result.time_s > 0 else 0
    
    # 速度范围校核
    if result.speed_mm_s > 500:
        result.warnings.append(f"速度 {result.speed_mm_s:.0f} mm/s 过快，建议加节流阀")
    elif result.speed_mm_s < 50:
        result.warnings.append(f"速度 {result.speed_mm_s:.0f} mm/s 过慢，可能爬行")
    
    return result


@dataclass
class TubeDiameterResult:
    """气管管径计算结果"""
    flow_l_min: float = 0.0
    pressure_mpa: float = 0.0
    max_velocity_m_s: float = 20.0      # 推荐最大流速 m/s
    recommended_od_mm: float = 0.0       # 推荐外径 mm
    recommended_id_mm: float = 0.0       # 推荐内径 mm
    warnings: List[str] = field(default_factory=list)


def tube_diameter_calculation(
    flow_l_min: float,
    pressure_mpa: float = 0.5,
    max_velocity_m_s: float = 20.0,
) -> TubeDiameterResult:
    """
    气管管径计算
    
    Args:
        flow_l_min: 流量 L/min (ANR)
        pressure_mpa: 工作压力 MPa
        max_velocity_m_s: 推荐最大流速 m/s
    
    Returns:
        TubeDiameterResult
    """
    result = TubeDiameterResult()
    result.flow_l_min = flow_l_min
    result.pressure_mpa = pressure_mpa
    result.max_velocity_m_s = max_velocity_m_s
    
    # 转换为实际状态流量
    # 标准状态流量转换为工作状态
    # Q_actual = Q_normal * P_normal / P_actual
    p_normal = 0.1013  # MPa
    p_actual = p_normal + pressure_mpa
    flow_actual = flow_l_min * p_normal / p_actual  # L/min
    
    # 转换为 m³/s
    flow_m3_s = flow_actual / 1000 / 60
    
    # 截面积 A = Q / v
    A = flow_m3_s / max_velocity_m_s  # m²
    
    # 内径
    id_m = math.sqrt(4 * A / math.pi)
    id_mm = id_m * 1000
    
    result.recommended_id_mm = id_mm
    
    # 标准气管外径
    standard_tubes = [
        (4, 2.5),   # OD4 x ID2.5
        (6, 4),     # OD6 x ID4
        (8, 5),     # OD8 x ID5
        (10, 6.5),  # OD10 x ID6.5
        (12, 8),    # OD12 x ID8
    ]
    
    for od, id_tube in standard_tubes:
        if id_tube >= id_mm:
            result.recommended_od_mm = od
            result.recommended_id_mm = id_tube
            break
    else:
        result.recommended_od_mm = 12
        result.recommended_id_mm = 8
        result.warnings.append("流量较大，建议选用更粗气管")
    
    return result


@dataclass
class VacuumSystemResult:
    """真空系统计算结果"""
    suction_cup_dia_mm: float = 0.0
    number_of_cups: int = 1
    vacuum_kpa: float = -60.0
    holding_force_n: float = 0.0
    flow_l_min: float = 0.0
    recommended_generator: str = ""
    warnings: List[str] = field(default_factory=list)


def vacuum_system_calculation(
    payload_kg: float,
    cup_diameter_mm: float,
    number_of_cups: int = 1,
    vacuum_kpa: float = -60.0,
    cycle_time_s: float = 2.0,
    safety_factor: float = 3.0,
) -> VacuumSystemResult:
    """
    真空系统计算
    
    Args:
        payload_kg: 负载重量 kg
        cup_diameter_mm: 吸盘直径 mm
        number_of_cups: 吸盘数量
        vacuum_kpa: 真空度 kPa
        cycle_time_s: 循环时间 s
        safety_factor: 安全系数
    
    Returns:
        VacuumSystemResult
    """
    result = VacuumSystemResult()
    result.suction_cup_dia_mm = cup_diameter_mm
    result.number_of_cups = number_of_cups
    result.vacuum_kpa = vacuum_kpa
    
    g = 9.81
    
    # 单吸盘吸力
    cup_area = math.pi * (cup_diameter_mm / 2000)**2  # m²
    single_force = abs(vacuum_kpa) * 1000 * cup_area  # N
    
    # 总吸力
    total_force = single_force * number_of_cups
    result.holding_force_n = total_force
    
    # 安全系数校核
    required_force = payload_kg * g * safety_factor
    if total_force < required_force:
        result.warnings.append(
            f"吸力不足: {total_force:.1f} N < 需要 {required_force:.1f} N"
        )
    
    # 耗气量估算 (真空发生器)
    # 每个吸盘容积 + 管路容积
    cup_volume = cup_area * 0.01 * 1000  # L (假设吸附深度10mm)
    total_volume = cup_volume * number_of_cups * 1.5  # 1.5倍管路余量
    
    # 流量计算
    flow = total_volume / cycle_time_s * 60  # L/min
    result.flow_l_min = flow
    
    # 推荐真空发生器
    if flow < 10:
        result.recommended_generator = "ZG1-06"
    elif flow < 30:
        result.recommended_generator = "ZG1-10"
    elif flow < 60:
        result.recommended_generator = "ZG2-16"
    else:
        result.recommended_generator = "真空泵"
        result.warnings.append("耗气量较大，建议选用真空泵")
    
    return result
