"""
联轴器选型计算

伺服/步进电机与丝杆/负载连接的联轴器选型。
公式来源: 米思米/松下/安川选型手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class CouplingResult:
    """联轴器选型结果"""
    torque_rating: float = 0.0           # 额定扭矩 N·m
    required_torque: float = 0.0         # 所需扭矩 N·m
    bore_size_motor: float = 0.0        # 电机轴径 mm
    bore_size_load: float = 0.0        # 负载轴径 mm
    inertia_kg_m2: float = 0.0         # 联轴器惯量 kg·m²
    max_speed_rpm: float = 0.0          # 最高转速 rpm
    recommended_type: str = ""          # 推荐类型
    recommended_size: str = ""          # 推荐规格
    warnings: List[str] = field(default_factory=list)


def coupling_selection(
    motor_torque_nm: float,
    motor_inertia_kg_m2: float = 0.0,
    load_inertia_kg_m2: float = 0.0,
    motor_shaft_dia: float = 14.0,
    load_shaft_dia: float = 12.0,
    max_speed_rpm: float = 3000.0,
    service_factor: float = 1.5,
) -> CouplingResult:
    """
    联轴器选型计算
    
    Args:
        motor_torque_nm: 电机额定扭矩 N·m
        motor_inertia_kg_m2: 电机惯量 kg·m²
        load_inertia_kg_m2: 负载惯量 kg·m²
        motor_shaft_dia: 电机轴径 mm
        load_shaft_dia: 负载轴径 mm
        max_speed_rpm: 最高转速 rpm
        service_factor: 工作系数
    
    Returns:
        CouplingResult
    """
    result = CouplingResult()
    
    # 所需扭矩
    required_torque = motor_torque_nm * service_factor
    result.required_torque = required_torque
    result.bore_size_motor = motor_shaft_dia
    result.bore_size_load = load_shaft_dia
    result.max_speed_rpm = max_speed_rpm
    
    # 联轴器类型选择
    if required_torque < 0.5:
        result.recommended_type = "膜片联轴器"
        result.recommended_size = "GK14"
        result.torque_rating = 1.5
        result.inertia_kg_m2 = 0.0000008
    elif required_torque < 2.0:
        result.recommended_type = "膜片联轴器"
        result.recommended_size = "GK20"
        result.torque_rating = 5.0
        result.inertia_kg_m2 = 0.000003
    elif required_torque < 10.0:
        result.recommended_type = "梅花联轴器"
        result.recommended_size = "LK30"
        result.torque_rating = 25.0
        result.inertia_kg_m2 = 0.000015
    else:
        result.recommended_type = "齿式联轴器"
        result.recommended_size = "GCL45"
        result.torque_rating = 100.0
        result.inertia_kg_m2 = 0.00008
        result.warnings.append("扭矩较大，建议选用更大型号")
    
    # 惯量校核
    if motor_inertia_kg_m2 > 0 and load_inertia_kg_m2 > 0:
        total_load_inertia = load_inertia_kg_m2 + result.inertia_kg_m2
        inertia_ratio = total_load_inertia / motor_inertia_kg_m2
        
        if inertia_ratio > 10:
            result.warnings.append(
                f"惯量比 {inertia_ratio:.1f} 过大，建议增大电机或降低减速比"
            )
    
    # 转速校核
    max_speed_allowed = {
        "GK14": 10000,
        "GK20": 8000,
        "LK30": 6000,
        "GCL45": 4000,
    }
    max_allowed = max_speed_allowed.get(result.recommended_size, 5000)
    if max_speed_rpm > max_allowed:
        result.warnings.append(
            f"转速 {max_speed_rpm:.0f} rpm 超过推荐值 {max_allowed} rpm"
        )
    
    return result


@dataclass
class TimingPulleyResult:
    """同步带轮选型结果"""
    pulley_teeth: int = 0               # 小带轮齿数
    large_pulley_teeth: int = 0         # 大带轮齿数
    pulley_dia_mm: float = 0.0          # 节圆直径 mm
    belt_width: float = 0.0             # 带宽 mm
    belt_length_mm: float = 0.0         # 带长 mm
    recommended_belt: str = ""          # 推荐带型
    warnings: List[str] = field(default_factory=list)


def timing_pulley_selection(
    motor_speed_rpm: float,
    output_speed_rpm: float,
    power_kw: float,
    center_distance: float = 150.0,
) -> TimingPulleyResult:
    """
    同步带轮选型计算
    
    Args:
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        power_kw: 传递功率 kW
        center_distance: 中心距 mm
    
    Returns:
        TimingPulleyResult
    """
    result = TimingPulleyResult()
    
    # 传动比
    ratio = motor_speed_rpm / output_speed_rpm
    
    # 小带轮齿数
    if motor_speed_rpm < 1800:
        small_teeth = 20
    elif motor_speed_rpm < 3600:
        small_teeth = 16
    else:
        small_teeth = 14
        result.warnings.append("转速较高，建议选用更多齿数")
    
    result.pulley_teeth = small_teeth
    result.large_pulley_teeth = round(small_teeth * ratio)
    
    # 带型选择
    if power_kw < 0.2:
        result.recommended_belt = "XL (5.08mm)"
        pitch = 5.08
    elif power_kw < 1.0:
        result.recommended_belt = "L (9.525mm)"
        pitch = 9.525
    elif power_kw < 3.0:
        result.recommended_belt = "H (12.7mm)"
        pitch = 12.7
    else:
        result.recommended_belt = "XH (19.05mm)"
        pitch = 19.05
        result.warnings.append("功率较大，建议选用更大型号")
    
    # 节圆直径
    result.pulley_dia_mm = small_teeth * pitch / math.pi
    
    # 带宽估算
    if power_kw < 0.5:
        result.belt_width = 9.5
    elif power_kw < 1.5:
        result.belt_width = 15.9
    else:
        result.belt_width = 25.4
    
    # 带长计算
    d1 = result.pulley_dia_mm
    d2 = result.large_pulley_teeth * pitch / math.pi
    belt_length = 2 * center_distance + math.pi / 2 * (d1 + d2) + (d2 - d1)**2 / (4 * center_distance)
    result.belt_length_mm = belt_length
    
    return result


@dataclass
class SprocketResult:
    """链轮选型结果"""
    sprocket_teeth: int = 0
    large_sprocket_teeth: int = 0
    chain_pitch: float = 0.0             # 节距 mm
    chain_length_links: int = 0          # 链长节数
    recommended_chain: str = ""
    warnings: List[str] = field(default_factory=list)


def sprocket_selection(
    motor_speed_rpm: float,
    output_speed_rpm: float,
    power_kw: float,
    center_distance: float = 300.0,
) -> SprocketResult:
    """
    链轮选型计算
    
    Args:
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        power_kw: 传递功率 kW
        center_distance: 中心距 mm
    
    Returns:
        SprocketResult
    """
    result = SprocketResult()
    
    # 传动比
    ratio = motor_speed_rpm / output_speed_rpm
    
    # 小链轮齿数
    result.sprocket_teeth = 17
    result.large_sprocket_teeth = round(17 * ratio)
    
    # 链条节距
    if power_kw < 0.5:
        result.chain_pitch = 9.525
        result.recommended_chain = "06B"
    elif power_kw < 1.5:
        result.chain_pitch = 12.7
        result.recommended_chain = "08A"
    elif power_kw < 4.0:
        result.chain_pitch = 15.875
        result.recommended_chain = "10A"
    else:
        result.chain_pitch = 19.05
        result.recommended_chain = "12A"
        result.warnings.append("功率较大，建议选用双排链")
    
    # 链长计算
    p = result.chain_pitch
    z1 = result.sprocket_teeth
    z2 = result.large_sprocket_teeth
    
    Lp = 2 * center_distance / p + (z1 + z2) / 2 + ((z2 - z1) / (2 * math.pi))**2 * p / center_distance
    result.chain_length_links = math.ceil(Lp)
    if result.chain_length_links % 2 != 0:
        result.chain_length_links += 1
    
    return result
