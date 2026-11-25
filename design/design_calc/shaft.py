"""
轴的强度校核计算

传动轴/心轴/转轴的强度校核。
公式来源: 机械设计手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ShaftResult:
    """轴强度校核结果"""
    bending_stress: float = 0.0         # 弯曲应力 MPa
    torsion_stress: float = 0.0         # 扭转应力 MPa
    equivalent_stress: float = 0.0      # 当量应力 MPa
    allowable_stress: float = 0.0       # 许用应力 MPa
    safety_factor: float = 0.0
    pass_strength: bool = False
    critical_speed: float = 0.0         # 临界转速 rpm
    warnings: List[str] = field(default_factory=list)


def shaft_strength_check(
    shaft_dia_mm: float,
    bending_moment_nmm: float = 0.0,
    torque_nmm: float = 0.0,
    material: str = "45钢",
) -> ShaftResult:
    """
    轴的强度校核 (弯扭组合变形)
    
    Args:
        shaft_dia_mm: 轴径 mm
        bending_moment_nmm: 弯矩 N·mm
        torque_nmm: 扭矩 N·mm
        material: 材料
    
    Returns:
        ShaftResult
    """
    result = ShaftResult()
    
    # 材料许用应力
    allowable_stress = {
        "45钢": 60,
        "40Cr": 90,
        "304不锈钢": 70,
    }.get(material, 60)
    result.allowable_stress = allowable_stress
    
    d = shaft_dia_mm
    
    # 抗弯截面系数
    W = math.pi * d**3 / 32  # mm³
    
    # 抗扭截面系数
    Wt = math.pi * d**3 / 16  # mm³
    
    # 弯曲应力
    if bending_moment_nmm > 0:
        result.bending_stress = bending_moment_nmm / W
    
    # 扭转应力
    if torque_nmm > 0:
        result.torsion_stress = torque_nmm / Wt
    
    # 当量应力 (第三强度理论)
    result.equivalent_stress = math.sqrt(
        result.bending_stress**2 + 4 * result.torsion_stress**2
    )
    
    # 安全系数
    if result.equivalent_stress > 0:
        result.safety_factor = allowable_stress / result.equivalent_stress
    
    # 校核
    result.pass_strength = result.safety_factor >= 1.5
    
    if not result.pass_strength and result.equivalent_stress > 0:
        result.warnings.append(
            f"强度不足，安全系数 {result.safety_factor:.2f} < 1.5"
        )
    
    # 临界转速估算 (简化)
    # n_c = 30 / π * sqrt(E*I*g / (m*L^4))
    # 这里用简化公式
    result.critical_speed = 10000 / d  # 经验值
    
    return result


@dataclass
class KeyResult:
    """键连接校核结果"""
    bearing_pressure: float = 0.0       # 挤压应力 MPa
    shear_stress: float = 0.0           # 剪应力 MPa
    allowable_bearing: float = 0.0      # 许用挤压应力 MPa
    safety_factor: float = 0.0
    pass_strength: bool = False
    warnings: List[str] = field(default_factory=list)


def key_connection_check(
    shaft_dia_mm: float,
    torque_nm: float,
    key_length_mm: float = 20.0,
    key_material: str = "45钢",
) -> KeyResult:
    """
    平键连接校核
    
    Args:
        shaft_dia_mm: 轴径 mm
        torque_nm: 传递扭矩 N·m
        key_length_mm: 键长 mm
        key_material: 键材料
    
    Returns:
        KeyResult
    """
    result = KeyResult()
    
    # 键尺寸 (根据轴径)
    # 标准平键: b x h
    if shaft_dia_mm <= 10:
        b, h = 3, 3
    elif shaft_dia_mm <= 12:
        b, h = 4, 4
    elif shaft_dia_mm <= 17:
        b, h = 5, 5
    elif shaft_dia_mm <= 22:
        b, h = 6, 6
    elif shaft_dia_mm <= 30:
        b, h = 8, 7
    elif shaft_dia_mm <= 38:
        b, h = 10, 8
    else:
        b, h = 12, 8
    
    # 许用挤压应力
    allowable_bearing = {
        "45钢": 100,
        "Q235": 80,
    }.get(key_material, 100)
    result.allowable_bearing = allowable_bearing
    
    d = shaft_dia_mm
    L = key_length_mm
    torque_nmm = torque_nm * 1000
    
    # 挤压力
    # p = 2T / (d*k*L), k = h/2
    k = h / 2
    result.bearing_pressure = 2 * torque_nmm / (d * k * L)
    
    # 剪切应力
    # τ = 2T / (d*b*L)
    result.shear_stress = 2 * torque_nmm / (d * b * L)
    
    # 安全系数
    result.safety_factor = allowable_bearing / result.bearing_pressure
    
    # 校核
    result.pass_strength = result.safety_factor >= 1.5
    
    if not result.pass_strength:
        result.warnings.append(
            f"键强度不足，安全系数 {result.safety_factor:.2f} < 1.5"
        )
    
    return result
