"""
轴承和链条传动计算

轴承寿命计算、链条传动选型。
公式来源: SKF/NSK 轴承选型手册、ISO 链条标准
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BearingResult:
    """轴承寿命计算结果"""
    dynamic_load_rating: float = 0.0    # 额定动载荷 kN
    equivalent_load: float = 0.0         # 等效动载荷 kN
    life_L10_hours: float = 0.0        # L10 寿命 小时
    life_L10_km: float = 0.0           # L10 寿命 km
    basic_rating: float = 0.0          # 基本额定寿命
    recommended_type: str = ""          # 推荐轴承类型
    warnings: list = field(default_factory=list)


def bearing_life_calculation(
    radial_load: float,
    axial_load: float = 0.0,
    speed_rpm: float = 1000.0,
    bearing_type: str = "deep_groove",
    required_life_hours: float = 20000.0,
) -> BearingResult:
    """
    轴承寿命计算

    Args:
        radial_load: 径向载荷 kN
        axial_load: 轴向载荷 kN
        speed_rpm: 转速 rpm
        bearing_type: 轴承类型 (deep_groove/angular_contact/roller)
        required_life_hours: 要求寿命 小时

    Returns:
        BearingResult
    """
    result = BearingResult()

    # 轴承类型系数
    # 球轴承寿命指数 p=3, 滚子轴承 p=10/3
    if bearing_type == "roller":
        p = 10.0 / 3.0
        result.recommended_type = "滚子轴承"
    else:
        p = 3.0
        if bearing_type == "angular_contact":
            result.recommended_type = "角接触球轴承"
        else:
            result.recommended_type = "深沟球轴承"

    # 等效动载荷计算
    # P = X*Fr + Y*Fa
    # 简化处理
    if axial_load > 0:
        # 有轴向载荷
        Fa_Fr_ratio = axial_load / radial_load if radial_load > 0 else 0
        if Fa_Fr_ratio > 0.1:
            X = 0.56
            Y = 1.5 - 0.3 * Fa_Fr_ratio  # 近似
        else:
            X = 1.0
            Y = 0.0
    else:
        X = 1.0
        Y = 0.0

    P = X * radial_load + Y * axial_load
    result.equivalent_load = P

    # 估算所需额定动载荷
    # L10 = (C/P)^p (百万转)
    # 换算成小时: L10h = 10^6 / (60*n) * (C/P)^p
    # => C = P * (L10h * 60*n / 10^6)^(1/p)

    required_L10 = required_life_hours * 60 * speed_rpm / 1e6
    C_required = P * (required_L10 ** (1.0 / p))

    result.dynamic_load_rating = C_required

    # 基本额定寿命 (假设选用标准轴承)
    # 这里用估算值
    C_estimated = C_required * 1.2  # 安全系数
    L10_million = (C_estimated / P) ** p
    result.basic_rating = L10_million

    # 寿命小时
    if speed_rpm > 0:
        result.life_L10_hours = (1e6 / (60 * speed_rpm)) * L10_million
    else:
        result.life_L10_hours = 999999

    # 寿命 km (如果是旋转轴，这里只做参考)
    result.life_L10_km = result.life_L10_hours * speed_rpm * 2 * math.pi / 1000 / 60

    # 推荐规格
    if C_required < 5:
        result.recommended_type += " 62xx系列"
    elif C_required < 15:
        result.recommended_type += " 63xx系列"
    elif C_required < 30:
        result.recommended_type += " 60xx系列 (大直径)"
    else:
        result.recommended_type += " 建议选用滚子轴承"
        result.warnings.append("载荷较大，建议选用滚子轴承")

    return result


@dataclass
class ChainResult:
    """链条传动计算结果"""
    chain_pitch: str = ""               # 链条节距
    chain_length_links: float = 0.0     # 链长 (节数)
    sprocket_ratio: float = 0.0         # 传动比
    chain_speed_m_s: float = 0.0        # 链速 m/s
    required_power_kw: float = 0.0     # 所需功率 kW
    center_distance: float = 0.0         # 中心距 mm
    tension_force_n: float = 0.0        # 张力 N
    warnings: list = field(default_factory=list)


def chain_drive_selection(
    motor_speed_rpm: float,
    output_speed_rpm: float,
    power_kw: float,
    center_distance: float = 300.0,
    small_sprocket_teeth: int = 17,
) -> ChainResult:
    """
    链条传动选型计算

    Args:
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        power_kw: 传递功率 kW
        center_distance: 中心距 mm
        small_sprocket_teeth: 小链轮齿数

    Returns:
        ChainResult
    """
    result = ChainResult()
    result.center_distance = center_distance
    result.required_power_kw = power_kw

    # 传动比
    ratio = motor_speed_rpm / output_speed_rpm
    result.sprocket_ratio = ratio

    # 大链轮齿数
    large_sprocket_teeth = round(small_sprocket_teeth * ratio)

    # 链条节距选择
    # 根据功率和转速选择
    chain_pitches = {
        "04C": 6.35,
        "06C": 9.525,
        "08A": 12.7,
        "10A": 15.875,
        "12A": 19.05,
        "16A": 25.4,
    }

    # 估算所需节距
    if power_kw < 0.5:
        result.chain_pitch = "06C"
    elif power_kw < 1.5:
        result.chain_pitch = "08A"
    elif power_kw < 4.0:
        result.chain_pitch = "10A"
    elif power_kw < 8.0:
        result.chain_pitch = "12A"
    else:
        result.chain_pitch = "16A"
        result.warnings.append("功率较大，建议选用双排链条")

    pitch = chain_pitches.get(result.chain_pitch, 9.525)

    # 链轮节圆直径
    d1 = pitch / math.sin(math.pi / small_sprocket_teeth)
    d2 = pitch / math.sin(math.pi / large_sprocket_teeth)

    # 链长计算 (节数)
    # Lp = 2*Cp/P + (Z1+Z2)/2 + ((Z2-Z1)/(2π))² * P/Cp
    Lp = 2 * center_distance / pitch + (small_sprocket_teeth + large_sprocket_teeth) / 2 + \
         ((large_sprocket_teeth - small_sprocket_teeth) / (2 * math.pi))**2 * pitch / center_distance

    result.chain_length_links = math.ceil(Lp)
    # 链长通常取偶数
    if result.chain_length_links % 2 != 0:
        result.chain_length_links += 1

    # 链速
    result.chain_speed_m_s = (math.pi * d1 * motor_speed_rpm) / (60 * 1000)

    # 最大链速校核
    max_speeds = {
        "04C": 25,
        "06C": 20,
        "08A": 15,
        "10A": 12,
        "12A": 10,
        "16A": 8,
    }
    max_v = max_speeds.get(result.chain_pitch, 15)
    if result.chain_speed_m_s > max_v:
        result.warnings.append(f"链速 {result.chain_speed_m_s:.1f} m/s 超过推荐值 {max_v} m/s")

    # 张力计算
    # F = 1000*P / v (N)
    if result.chain_speed_m_s > 0:
        result.tension_force_n = 1000 * power_kw / result.chain_speed_m_s
    else:
        result.tension_force_n = 0

    return result


@dataclass
class ConveyorResult:
    """传送带计算结果"""
    belt_speed_m_min: float = 0.0      # 带速 m/min
    belt_width: float = 0.0           # 带宽 mm
    required_motor_kw: float = 0.0    # 所需电机功率 kW
    conveyor_length: float = 0.0       # 输送长度 m
    capacity_kg_h: float = 0.0        # 输送能力 kg/h
    cycle_time_s: float = 0.0         # 节拍时间 s
    warnings: list = field(default_factory=list)


def conveyor_calculation(
    material_weight_kg: float,
    conveyor_length: float = 1.0,
    belt_speed_m_min: float = 10.0,
    friction_coeff: float = 0.02,
    incline_angle_deg: float = 0.0,
    number_of_parts: int = 1,
) -> ConveyorResult:
    """
    传送带输送计算

    Args:
        material_weight_kg: 单件重量 kg
        conveyor_length: 输送长度 m
        belt_speed_m_min: 带速 m/min
        friction_coeff: 摩擦系数
        incline_angle_deg: 倾斜角度 度
        number_of_parts: 同时在输送线上的工件数

    Returns:
        ConveyorResult
    """
    result = ConveyorResult()
    result.conveyor_length = conveyor_length
    result.belt_speed_m_min = belt_speed_m_min

    g = 9.81

    # 总重量
    total_weight = material_weight_kg * number_of_parts

    # 运行阻力
    # 水平阻力
    horizontal_force = total_weight * g * friction_coeff

    # 倾斜阻力
    incline_rad = math.radians(incline_angle_deg)
    incline_force = total_weight * g * math.sin(incline_rad)

    total_force = horizontal_force + incline_force

    # 所需功率
    # P = F * v / (1000 * η)
    v_m_s = belt_speed_m_min / 60.0
    efficiency = 0.85
    result.required_motor_kw = total_force * v_m_s / (1000 * efficiency)

    # 考虑安全系数
    result.required_motor_kw *= 1.5

    # 输送能力
    # 每小时输送件数
    if conveyor_length > 0:
        parts_per_hour = (v_m_s * 3600) / conveyor_length
        result.capacity_kg_h = parts_per_hour * material_weight_kg
    else:
        result.capacity_kg_h = 0

    # 节拍时间 (秒/件)
    if v_m_s > 0:
        result.cycle_time_s = conveyor_length / v_m_s
    else:
        result.cycle_time_s = 0

    # 推荐带宽
    if material_weight_kg < 1:
        result.belt_width = 50
    elif material_weight_kg < 5:
        result.belt_width = 100
    elif material_weight_kg < 20:
        result.belt_width = 150
    else:
        result.belt_width = 200
        result.warnings.append("工件较重，建议选用更宽皮带或链板线")

    return result
