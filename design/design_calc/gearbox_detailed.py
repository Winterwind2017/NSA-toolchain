"""
减速机详细选型计算

谐波减速机、行星减速机详细选型计算。
公式来源: 新宝/哈默纳克/纽氏达特选型手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class HarmonicGearboxResult:
    """谐波减速机选型结果"""
    model: str = ""                      # 推荐型号
    ratio: float = 0.0                  # 减速比
    rated_torque: float = 0.0           # 额定扭矩 N·m
    max_torque: float = 0.0            # 最大扭矩 N·m
    backlash_arcmin: float = 0.0       # 背隙 arcmin
    inertia_kg_m2: float = 0.0          # 减速机惯量 kg·m²
    efficiency: float = 0.8             # 效率
    warnings: List[str] = field(default_factory=list)


def harmonic_gearbox_selection(
    load_torque_nm: float,
    motor_speed_rpm: float = 3000.0,
    output_speed_rpm: float = 120.0,
    peak_torque_nm: float = 0.0,
    precision: str = "standard",
) -> HarmonicGearboxResult:
    """
    谐波减速机选型计算
    
    Args:
        load_torque_nm: 负载额定扭矩 N·m
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        peak_torque_nm: 峰值扭矩 N·m
        precision: 精度等级 (standard/high)
    
    Returns:
        HarmonicGearboxResult
    """
    result = HarmonicGearboxResult()
    
    # 减速比
    result.ratio = motor_speed_rpm / output_speed_rpm
    
    # 峰值扭矩
    if peak_torque_nm == 0:
        peak_torque_nm = load_torque_nm * 2
    
    # 型号选择 (根据扭矩)
    gearbox_models = [
        # (型号, 额定扭矩, 最大扭矩, 背隙, 惯量)
        ("CSF-14", 4.0, 11.0, 1.0, 0.0000004),
        ("CSF-17", 8.0, 22.0, 1.0, 0.0000015),
        ("CSF-20", 16.0, 45.0, 0.5, 0.000004),
        ("CSF-25", 32.0, 90.0, 0.5, 0.000012),
        ("CSF-32", 65.0, 180.0, 0.5, 0.00004),
        ("CSF-40", 130.0, 360.0, 0.5, 0.00012),
    ]
    
    for model, rated, max_tor, backlash, inertia in gearbox_models:
        if load_torque_nm <= rated:
            result.model = model
            result.rated_torque = rated
            result.max_torque = max_tor
            result.backlash_arcmin = backlash if precision == "high" else backlash * 2
            result.inertia_kg_m2 = inertia
            break
    else:
        result.model = "CSF-40"
        result.rated_torque = 130.0
        result.max_torque = 360.0
        result.warnings.append("扭矩过大，建议选用更大型号或并联方案")
    
    # 校核峰值扭矩
    if peak_torque_nm > result.max_torque:
        result.warnings.append(
            f"峰值扭矩 {peak_torque_nm:.1f} N·m 超过最大扭矩 {result.max_torque:.1f} N·m"
        )
    
    return result


@dataclass
class PlanetaryGearboxResult:
    """行星减速机选型结果"""
    model: str = ""
    ratio: float = 0.0
    rated_torque: float = 0.0
    max_torque: float = 0.0
    backlash_arcmin: float = 0.0
    inertia_kg_m2: float = 0.0
    efficiency: float = 0.97
    warnings: List[str] = field(default_factory=list)


def planetary_gearbox_selection(
    load_torque_nm: float,
    motor_speed_rpm: float = 3000.0,
    output_speed_rpm: float = 100.0,
    peak_torque_nm: float = 0.0,
    motor_size: str = "60",
) -> PlanetaryGearboxResult:
    """
    行星减速机选型计算
    
    Args:
        load_torque_nm: 负载额定扭矩 N·m
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        peak_torque_nm: 峰值扭矩 N·m
        motor_size: 电机机座号 (42/60/80/90)
    
    Returns:
        PlanetaryGearboxResult
    """
    result = PlanetaryGearboxResult()
    
    # 减速比
    result.ratio = motor_speed_rpm / output_speed_rpm
    
    # 峰值扭矩
    if peak_torque_nm == 0:
        peak_torque_nm = load_torque_nm * 2
    
    # 型号选择 (根据电机机座号和扭矩)
    gearbox_models = {
        "42": [
            ("PLE42-5", 2.0, 6.0, 8.0, 0.0000005),
            ("PLE42-10", 4.0, 12.0, 8.0, 0.0000008),
        ],
        "60": [
            ("PLE60-5", 8.0, 25.0, 6.0, 0.000003),
            ("PLE60-10", 16.0, 50.0, 6.0, 0.000005),
            ("PLE60-20", 25.0, 75.0, 6.0, 0.000008),
        ],
        "80": [
            ("PLE80-5", 30.0, 90.0, 5.0, 0.000015),
            ("PLE80-10", 60.0, 180.0, 5.0, 0.000025),
            ("PLE80-20", 100.0, 300.0, 5.0, 0.00004),
        ],
        "90": [
            ("PLE90-5", 80.0, 240.0, 5.0, 0.00005),
            ("PLE90-10", 160.0, 480.0, 5.0, 0.00008),
            ("PLE90-20", 250.0, 750.0, 5.0, 0.00012),
        ],
    }
    
    models = gearbox_models.get(motor_size, gearbox_models["60"])
    
    for model, rated, max_tor, backlash, inertia in models:
        if load_torque_nm <= rated:
            result.model = model
            result.rated_torque = rated
            result.max_torque = max_tor
            result.backlash_arcmin = backlash
            result.inertia_kg_m2 = inertia
            break
    else:
        result.model = models[-1][0]
        result.rated_torque = models[-1][1]
        result.warnings.append("扭矩过大，建议选用更大机座号")
    
    # 校核峰值扭矩
    if peak_torque_nm > result.max_torque:
        result.warnings.append(
            f"峰值扭矩 {peak_torque_nm:.1f} N·m 超过最大扭矩 {result.max_torque:.1f} N·m"
        )
    
    return result
