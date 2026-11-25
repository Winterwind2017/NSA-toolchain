"""
机械手负载计算

直角机械手/六轴机械手负载能力计算。
公式来源: 非标自动化设计手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class RobotLoadResult:
    """机械手负载计算结果"""
    payload_kg: float = 0.0            # 负载重量 kg
    arm_length_mm: float = 0.0         # 臂长 mm
    inertia_kg_m2: float = 0.0          # 负载惯量 kg·m²
    torque_nm: float = 0.0             # 所需扭矩 N·m
    recommended_robot: str = ""          # 推荐机械手
    warnings: List[str] = field(default_factory=list)


def gantry_robot_calculation(
    payload_kg: float,
    arm_length_mm: float,
    acceleration_m_s2: float = 5.0,
    vertical: bool = True,
) -> RobotLoadResult:
    """
    直角机械手负载计算
    
    Args:
        payload_kg: 负载重量 kg
        arm_length_mm: 水平臂长 mm
        acceleration_m_s2: 加速度 m/s²
        vertical: 是否竖直方向
    
    Returns:
        RobotLoadResult
    """
    result = RobotLoadResult()
    result.payload_kg = payload_kg
    result.arm_length_mm = arm_length_mm
    
    g = 9.81
    r = arm_length_mm / 1000  # 转换为 m
    
    # 负载惯量 (简化为质点)
    result.inertia_kg_m2 = payload_kg * r**2
    
    # 所需扭矩
    # 重力扭矩 + 加速扭矩
    if vertical:
        gravity_torque = payload_kg * g * r
    else:
        gravity_torque = 0
    
    # 加速扭矩
    angular_accel = acceleration_m_s2 / r  # α = a/r
    accel_torque = result.inertia_kg_m2 * angular_accel
    
    result.torque_nm = (gravity_torque + accel_torque) * 2.0  # 2倍安全系数
    
    # 推荐机械手
    if result.torque_nm < 10:
        result.recommended_robot = "单轴机械手 (5kg)"
    elif result.torque_nm < 30:
        result.recommended_robot = "单轴机械手 (10kg)"
    elif result.torque_nm < 80:
        result.recommended_robot = "两轴机械手 (20kg)"
    else:
        result.recommended_robot = "三轴机械手 (50kg)"
        result.warnings.append("负载较大，建议选用更大型号")
    
    return result


@dataclass
class ConveyorResult:
    """传送带计算结果"""
    belt_width_mm: float = 0.0
    belt_speed_m_min: float = 0.0
    motor_power_kw: float = 0.0
    recommended_motor: str = ""
    warnings: List[str] = field(default_factory=list)


def conveyor_calculation(
    payload_kg: float,
    length_m: float,
    speed_m_min: float = 10.0,
    incline_deg: float = 0.0,
) -> ConveyorResult:
    """
    传送带计算
    
    Args:
        payload_kg: 单件重量 kg
        length_m: 传送带长度 m
        speed_m_min: 速度 m/min
        incline_deg: 倾斜角度 度
    
    Returns:
        ConveyorResult
    """
    result = ConveyorResult()
    
    g = 9.81
    
    # 传送带宽度估算
    if payload_kg < 5:
        result.belt_width_mm = 100
    elif payload_kg < 10:
        result.belt_width_mm = 150
    elif payload_kg < 30:
        result.belt_width_mm = 200
    else:
        result.belt_width_mm = 300
        result.warnings.append("负载较大，建议滚筒线")
    
    result.belt_speed_m_min = speed_m_min
    
    # 阻力计算
    # 运行阻力 = 摩擦阻力 + 提升阻力
    friction_force = payload_kg * g * 0.02  # 摩擦系数 0.02
    
    # 提升阻力 (如果倾斜)
    incline_rad = math.radians(incline_deg)
    lift_force = payload_kg * g * math.sin(incline_rad)
    
    total_force = friction_force + lift_force
    
    # 电机功率
    # P = F * v / (η * 1000)
    v = speed_m_min / 60  # m/s
    efficiency = 0.7
    power_kw = total_force * v / (efficiency * 1000)
    
    result.motor_power_kw = power_kw
    
    # 推荐电机
    if power_kw < 0.1:
        result.recommended_motor = "24V 直流电机 100W"
    elif power_kw < 0.3:
        result.recommended_motor = "220V 交流电机 200W"
    elif power_kw < 0.75:
        result.recommended_motor = "380V 交流电机 400W"
    else:
        result.recommended_motor = "380V 交流电机 750W"
    
    return result


@dataclass
class IndexerResult:
    """凸轮分割器选型结果"""
    model: str = ""
    stations: int = 0
    torque_nm: float = 0.0
    index_angle_deg: float = 0.0
    stop_angle_deg: float = 0.0
    warnings: List[str] = field(default_factory=list)


def cam_indexer_selection(
    load_torque_nm: float,
    stations: int = 4,
    index_time_s: float = 0.5,
) -> IndexerResult:
    """
    凸轮分割器选型计算
    
    Args:
        load_torque_nm: 负载扭矩 N·m
        stations: 工位数
        index_time_s: 分度时间 s
    
    Returns:
        IndexerResult
    """
    result = IndexerResult()
    result.stations = stations
    result.torque_nm = load_torque_nm
    
    # 分割角度
    result.index_angle_deg = 360 / stations
    
    # 推荐型号
    indexer_models = [
        ("RU45", 10, 0.5),
        ("RU60", 25, 1.0),
        ("RU80", 60, 2.0),
        ("RU100", 120, 4.0),
        ("RU140", 300, 10.0),
    ]
    
    for model, torque, index_angle in indexer_models:
        if load_torque_nm <= torque:
            result.model = model
            break
    else:
        result.model = "RU140"
        result.warnings.append("扭矩较大，建议选用更大型号")
    
    return result
