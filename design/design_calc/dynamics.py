"""
动力学计算

惯量匹配、翻转扭矩、提升力、顶升力、减速比优化等。
公式来源: 机械设计手册、非标自动化设计经验
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class InertiaMatchResult:
    """惯量匹配计算结果"""
    load_inertia: float = 0.0           # 负载惯量 kg·m²
    motor_inertia: float = 0.0          # 电机惯量 kg·m²
    inertia_ratio: float = 0.0          # 惯量比
    recommended_ratio: float = 0.0       # 推荐惯量比
    match_ok: bool = False               # 是否匹配
    recommended_reduction: float = 0.0   # 推荐减速比
    warnings: List[str] = field(default_factory=list)


def inertia_matching(
    load_inertia_kg_m2: float,
    motor_inertia_kg_m2: float,
    current_ratio: float = 1.0,
    max_ratio: float = 10.0,
) -> InertiaMatchResult:
    """
    惯量匹配计算
    
    Args:
        load_inertia_kg_m2: 负载惯量 kg·m²
        motor_inertia_kg_m2: 电机惯量 kg·m²
        current_ratio: 当前减速比
        max_ratio: 最大允许惯量比
    
    Returns:
        InertiaMatchResult
    """
    result = InertiaMatchResult()
    result.load_inertia = load_inertia_kg_m2
    result.motor_inertia = motor_inertia_kg_m2
    result.recommended_ratio = max_ratio
    
    # 折算到电机轴的惯量
    reflected_inertia = load_inertia_kg_m2 / (current_ratio ** 2)
    result.inertia_ratio = reflected_inertia / motor_inertia_kg_m2
    
    # 判断是否匹配
    result.match_ok = result.inertia_ratio <= max_ratio
    
    if not result.match_ok:
        # 计算所需减速比
        # I_load / i² / I_motor <= max_ratio
        # i >= sqrt(I_load / (I_motor * max_ratio))
        required_ratio = math.sqrt(
            load_inertia_kg_m2 / (motor_inertia_kg_m2 * max_ratio)
        )
        result.recommended_reduction = math.ceil(required_ratio * 10) / 10
        result.warnings.append(
            f"惯量比 {result.inertia_ratio:.1f} 过大，建议减速比 ≥ {result.recommended_reduction:.1f}"
        )
    
    return result


@dataclass
class FlipTorqueResult:
    """翻转扭矩计算结果"""
    weight_kg: float = 0.0
    center_of_mass_mm: float = 0.0      # 重心到旋转中心距离 mm
    gravity_torque: float = 0.0         # 重力扭矩 N·m
    accel_torque: float = 0.0           # 加速扭矩 N·m
    total_torque: float = 0.0           # 总扭矩 N·m
    recommended_motor_kw: float = 0.0  # 推荐电机功率 kW
    warnings: List[str] = field(default_factory=list)


def flip_torque_calculation(
    weight_kg: float,
    center_of_mass_mm: float,
    flip_time_s: float = 1.0,
    flip_angle_deg: float = 180.0,
    safety_factor: float = 2.0,
) -> FlipTorqueResult:
    """
    翻转扭矩计算
    
    Args:
        weight_kg: 翻转重量 kg
        center_of_mass_mm: 重心到旋转中心距离 mm
        flip_time_s: 翻转时间 s
        flip_angle_deg: 翻转角度 度
        safety_factor: 安全系数
    
    Returns:
        FlipTorqueResult
    """
    result = FlipTorqueResult()
    result.weight_kg = weight_kg
    result.center_of_mass_mm = center_of_mass_mm
    
    g = 9.81
    r = center_of_mass_mm / 1000  # 转换为 m
    
    # 重力产生的最大扭矩
    gravity_torque = weight_kg * g * r
    result.gravity_torque = gravity_torque
    
    # 加速扭矩计算
    # 角加速度 α = θ / t² (简化)
    angle_rad = math.radians(flip_angle_deg)
    angular_accel = angle_rad / (flip_time_s ** 2)
    
    # 转动惯量 (简化为质点)
    inertia = weight_kg * r ** 2
    
    accel_torque = inertia * angular_accel
    result.accel_torque = accel_torque
    
    # 总扭矩
    total_torque = (gravity_torque + accel_torque) * safety_factor
    result.total_torque = total_torque
    
    # 推荐电机功率
    # P = T * ω / 1000
    avg_speed = angle_rad / flip_time_s
    result.recommended_motor_kw = total_torque * avg_speed / 1000 * 1.5  # 1.5倍余量
    
    return result


@dataclass
class LiftForceResult:
    """提升/顶升力计算结果"""
    total_weight_kg: float = 0.0
    friction_force: float = 0.0          # 摩擦力 N
    gravity_force: float = 0.0          # 重力 N
    accel_force: float = 0.0            # 加速力 N
    total_force: float = 0.0             # 总提升力 N
    recommended_cylinder_bore: float = 0.0  # 推荐气缸缸径 mm
    warnings: List[str] = field(default_factory=list)


def lift_force_calculation(
    weight_kg: float,
    acceleration_mm_s2: float = 0.0,
    friction_coeff: float = 0.02,
    pressure_mpa: float = 0.5,
    safety_factor: float = 1.5,
) -> LiftForceResult:
    """
    提升/顶升力计算
    
    Args:
        weight_kg: 提升重量 kg
        acceleration_mm_s2: 加速度 mm/s²
        friction_coeff: 摩擦系数
        pressure_mpa: 气压 MPa
        safety_factor: 安全系数
    
    Returns:
        LiftForceResult
    """
    result = LiftForceResult()
    result.total_weight_kg = weight_kg
    
    g = 9.81
    
    # 重力
    gravity_force = weight_kg * g
    result.gravity_force = gravity_force
    
    # 摩擦力 (如果是水平导向)
    friction_force = weight_kg * g * friction_coeff
    result.friction_force = friction_force
    
    # 加速力
    accel = acceleration_mm_s2 / 1000  # 转换为 m/s²
    accel_force = weight_kg * accel
    result.accel_force = accel_force
    
    # 总力
    total_force = (gravity_force + friction_force + accel_force) * safety_factor
    result.total_force = total_force
    
    # 推荐气缸缸径
    # F = P * A = P * π * d² / 4
    # d = sqrt(4F / (π * P))
    pressure_pa = pressure_mpa * 1e6
    bore_m = math.sqrt(4 * total_force / (math.pi * pressure_pa))
    result.recommended_cylinder_bore = bore_m * 1000  # 转换为 mm
    
    return result


@dataclass
class GearRatioResult:
    """减速比优化结果"""
    load_speed_rpm: float = 0.0
    motor_speed_rpm: float = 3000.0
    reduction_ratio: float = 0.0
    motor_torque_needed: float = 0.0
    load_torque: float = 0.0
    efficiency: float = 0.9
    warnings: List[str] = field(default_factory=list)


def gear_ratio_optimization(
    load_torque_nm: float,
    load_speed_rpm: float,
    motor_rated_speed: float = 3000.0,
    motor_rated_torque: float = 1.27,
    efficiency: float = 0.9,
) -> GearRatioResult:
    """
    减速比优化计算
    
    Args:
        load_torque_nm: 负载所需扭矩 N·m
        load_speed_rpm: 负载所需转速 rpm
        motor_rated_speed: 电机额定转速 rpm
        motor_rated_torque: 电机额定扭矩 N·m
        efficiency: 减速机效率
    
    Returns:
        GearRatioResult
    """
    result = GearRatioResult()
    result.load_torque = load_torque_nm
    result.load_speed_rpm = load_speed_rpm
    result.motor_speed_rpm = motor_rated_speed
    result.efficiency = efficiency
    
    # 计算减速比
    result.reduction_ratio = motor_rated_speed / load_speed_rpm
    
    # 校核扭矩
    # T_load = T_motor * i * η
    # T_motor = T_load / (i * η)
    result.motor_torque_needed = load_torque_nm / (result.reduction_ratio * efficiency)
    
    if result.motor_torque_needed > motor_rated_torque:
        result.warnings.append(
            f"所需电机扭矩 {result.motor_torque_needed:.2f} N·m 超过额定值 {motor_rated_torque} N·m"
        )
    
    return result
