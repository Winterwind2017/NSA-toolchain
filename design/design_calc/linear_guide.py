"""
直线导轨选型计算

负载能力、寿命计算、力矩校核。
公式来源: THK/HIWIN/上银导轨选型手册、非标自动化设计经验
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class GuideSelectionResult:
    """直线导轨选型结果"""
    load_rating: float = 0.0           # 额定动载荷 kN
    max_static_load: float = 0.0       # 最大静态载荷 kN
    equivalent_load: float = 0.0      # 等效载荷 kN
    life_km: float = 0.0              # 额定寿命 km
    life_hours: float = 0.0           # 额定寿命 小时
    safety_factor: float = 0.0        # 安全系数
    recommended_size: str = ""         # 推荐导轨规格
    warnings: list = field(default_factory=list)


def linear_guide_selection(
    horizontal_load: float,
    vertical_load: float,
    moment_load: float = 0.0,
    stroke_length: float = 500.0,
    max_speed: float = 500.0,
    duty_cycle: float = 0.5,
    operation_hours_per_day: float = 8.0,
    required_life_years: float = 5.0,
    number_of_blocks: int = 2,
    guide_pitch: float = 40.0,
) -> GuideSelectionResult:
    """
    直线导轨选型计算

    Args:
        horizontal_load: 水平方向载荷 kg
        vertical_load: 垂直方向载荷 kg (向下为正)
        moment_load: 倾覆力矩 N·m
        stroke_length: 行程长度 mm
        max_speed: 最大速度 mm/s
        duty_cycle: 负载占空比 0~1
        operation_hours_per_day: 每天运行小时数
        required_life_years: 期望寿命 年
        number_of_blocks: 滑块数量
        guide_pitch: 导轨间距 mm

    Returns:
        GuideSelectionResult
    """
    result = GuideSelectionResult()

    g = 9.81  # m/s²

    # 计算实际载荷
    h_load_n = horizontal_load * g
    v_load_n = vertical_load * g

    # 单滑块平均载荷
    total_load_n = math.sqrt(h_load_n**2 + v_load_n**2)
    per_block_load = total_load_n / number_of_blocks

    # 倾覆力矩引起的附加载荷
    if moment_load > 0 and guide_pitch > 0:
        moment_per_block = (moment_load * 1000) / guide_pitch  # N
        per_block_load = math.sqrt(per_block_load**2 + moment_per_block**2)

    result.equivalent_load = per_block_load / 1000.0  # kN

    # 估算所需导轨规格
    # 常见导轨规格的额定动载荷 (参考值)
    guide_sizes = {
        "15": {"load_rating": 8.8, "max_static": 13.7},
        "20": {"load_rating": 14.2, "max_static": 21.8},
        "25": {"load_rating": 22.4, "max_static": 34.5},
        "30": {"load_rating": 35.4, "max_static": 52.2},
        "35": {"load_rating": 49.0, "max_static": 71.5},
    }

    required_static_load = (per_block_load / 1000.0) * 3.0  # 静态安全系数≥3

    selected_size = "25"
    for size, specs in sorted(guide_sizes.items(), key=lambda x: int(x[0])):
        if specs["max_static"] >= required_static_load:
            selected_size = size
            break
    else:
        selected_size = "35"
        result.warnings.append("载荷较大，建议选用35或更大规格导轨")

    result.recommended_size = f"HG{selected_size}"
    specs = guide_sizes.get(selected_size, guide_sizes["25"])
    result.load_rating = specs["load_rating"]
    result.max_static_load = specs["max_static"]

    # 寿命计算
    # L = (C/P)^3 * 50 km (球导轨)
    C = specs["load_rating"]  # kN
    P = result.equivalent_load  # kN

    if P > 0:
        life_km = ((C / P) ** 3) * 50.0
    else:
        life_km = 9999.0

    result.life_km = life_km

    # 换算成小时
    # 每分钟移动距离 = speed * 60 / 1000 m
    speed_m_per_min = max_speed * 60 / 1000.0
    if speed_m_per_min > 0:
        # 每小时移动距离
        distance_per_hour = speed_m_per_min * 60 * duty_cycle
        result.life_hours = (life_km * 1000) / distance_per_hour if distance_per_hour > 0 else 999999

    # 安全系数
    result.safety_factor = result.max_static_load / (result.equivalent_load * 3) if result.equivalent_load > 0 else 999

    # 校核
    if result.life_hours < required_life_years * 365 * operation_hours_per_day:
        result.warnings.append(
            f"预期寿命不足 {required_life_years} 年，建议增大导轨规格"
        )

    if result.safety_factor < 3:
        result.warnings.append("静态安全系数不足3，建议增大规格")

    return result


@dataclass
class TimingBeltResult:
    """同步带传动计算结果"""
    belt_pitch: str = ""               # 带型 (MXL/XL/L/H)
    belt_length_mm: float = 0.0        # 带长 mm
    pulley_ratio: float = 0.0          # 传动比
    belt_speed_m_s: float = 0.0       # 带速 m/s
    tension_ratio: float = 0.0         # 张力比
    required_width: float = 0.0        # 所需带宽 mm
    max_power_kw: float = 0.0          # 最大传递功率 kW
    center_distance: float = 0.0       # 中心距 mm
    warnings: list = field(default_factory=list)


def timing_belt_selection(
    motor_speed_rpm: float,
    output_speed_rpm: float,
    power_kw: float,
    center_distance: float = 100.0,
    small_pulley_teeth: int = 20,
) -> TimingBeltResult:
    """
    同步带传动选型计算

    Args:
        motor_speed_rpm: 电机转速 rpm
        output_speed_rpm: 输出转速 rpm
        power_kw: 传递功率 kW
        center_distance: 中心距 mm
        small_pulley_teeth: 小带轮齿数

    Returns:
        TimingBeltResult
    """
    result = TimingBeltResult()
    result.center_distance = center_distance

    # 传动比
    ratio = motor_speed_rpm / output_speed_rpm
    result.pulley_ratio = ratio

    # 大带轮齿数
    large_pulley_teeth = round(small_pulley_teeth * ratio)

    # 节距 (参考值)
    belt_pitches = {
        "MXL": 2.032,
        "XL": 5.08,
        "L": 9.525,
        "H": 12.7,
    }

    # 估算带型
    # 根据功率和转速选择
    if power_kw < 0.2 and motor_speed_rpm < 1800:
        result.belt_pitch = "XL"
    elif power_kw < 1.0:
        result.belt_pitch = "L"
    elif power_kw < 3.0:
        result.belt_pitch = "H"
    else:
        result.belt_pitch = "H"
        result.warnings.append("功率较大，建议选用更大型号或链条传动")

    pitch = belt_pitches.get(result.belt_pitch, 5.08)

    # 带轮节圆直径
    d1 = small_pulley_teeth * pitch / math.pi
    d2 = large_pulley_teeth * pitch / math.pi

    # 带长计算
    # L = 2*C + π/2*(d1+d2) + (d2-d1)²/(4*C)
    belt_length = 2 * center_distance + math.pi / 2 * (d1 + d2) + (d2 - d1)**2 / (4 * center_distance)
    result.belt_length_mm = belt_length

    # 带速
    result.belt_speed_m_s = (math.pi * d1 * motor_speed_rpm) / (60 * 1000)

    # 最大带速校核
    max_speed_limits = {"MXL": 40, "XL": 50, "L": 60, "H": 80}
    max_v = max_speed_limits.get(result.belt_pitch, 40)
    if result.belt_speed_m_s > max_v:
        result.warnings.append(f"带速 {result.belt_speed_m_s:.1f} m/s 超过推荐值 {max_v} m/s")

    # 所需带宽估算
    # 简化估算: 每mm带宽传递功率约
    power_per_mm = {
        "MXL": 0.02,
        "XL": 0.05,
        "L": 0.15,
        "H": 0.4,
    }
    p_per_mm = power_per_mm.get(result.belt_pitch, 0.05)
    result.required_width = power_kw / p_per_mm * 1.2  # 1.2倍安全系数

    # 标准带宽
    standard_widths = {
        "MXL": [3.2, 4.8, 6.4],
        "XL": [6.4, 7.9, 9.5, 12.7],
        "L": [12.7, 19.1, 25.4],
        "H": [19.1, 25.4, 38.1, 50.8],
    }
    widths = standard_widths.get(result.belt_pitch, [6.4, 9.5])
    for w in widths:
        if w >= result.required_width:
            result.required_width = w
            break
    else:
        result.required_width = widths[-1]
        result.warnings.append("需要更大带宽，建议选用更大型号")

    # 最大传递功率
    result.max_power_kw = result.required_width * p_per_mm

    return result


@dataclass
class SpringResult:
    """弹簧设计计算结果"""
    wire_diameter: float = 0.0         # 线径 mm
    outer_diameter: float = 0.0         # 外径 mm
    free_length: float = 0.0            # 自由长度 mm
    active_coils: float = 0.0          # 有效圈数
    spring_rate: float = 0.0            # 弹簧刚度 N/mm
    max_deflection: float = 0.0         # 最大变形量 mm
    max_force: float = 0.0             # 最大载荷 N
    shear_stress: float = 0.0          # 切应力 MPa
    safety_factor: float = 0.0          # 安全系数
    warnings: list = field(default_factory=list)


def compression_spring_design(
    required_force: float,
    required_deflection: float,
    max_outer_diameter: float = 20.0,
    material: str = "SWC",
    ends_type: str = "closed_ground",
) -> SpringResult:
    """
    压缩弹簧设计计算

    Args:
        required_force: 所需载荷 N
        required_deflection: 所需变形量 mm
        max_outer_diameter: 最大外径限制 mm
        material: 材料 (SWC/SWM/SS)
        ends_type: 端部形式 (closed_ground/closed/open)

    Returns:
        SpringResult
    """
    result = SpringResult()

    # 弹簧刚度
    k = required_force / required_deflection
    result.spring_rate = k

    # 弹簧材料切变模量
    G = {
        "SWC": 79000,   # 碳素弹簧钢
        "SWM": 79000,   # 合金弹簧钢
        "SS": 72000,    # 不锈钢
    }.get(material, 79000)

    # 许用切应力
    tau_allow = {
        "SWC": 550,
        "SWM": 700,
        "SS": 450,
    }.get(material, 550)

    # 初选线径 (经验公式)
    # d ≈ sqrt(8*K*D*F / π*τ)
    # 先假设旋绕比 C = 6
    C = 6.0
    D = max_outer_diameter * 0.8  # 中径约为外径的80%
    d = D / C

    # 圆整到标准线径
    standard_diameters = [0.5, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 8.0]
    for std_d in standard_diameters:
        if std_d >= d:
            d = std_d
            break
    else:
        d = standard_diameters[-1]

    result.wire_diameter = d
    D = d * C
    result.outer_diameter = D + d

    # 有效圈数
    # k = G*d^4 / (8*D^3*n)
    n = G * d**4 / (8 * D**3 * k)
    result.active_coils = round(n, 1)

    # 总圈数
    if ends_type == "closed_ground":
        total_coils = result.active_coils + 2
    elif ends_type == "closed":
        total_coils = result.active_coils + 1.5
    else:
        total_coils = result.active_coils + 1

    # 切应力计算
    # Wahl 修正系数
    K_w = (4*C - 1) / (4*C - 4) + 0.615 / C
    tau = K_w * (8 * required_force * D) / (math.pi * d**3)
    result.shear_stress = tau

    # 安全系数
    result.safety_factor = tau_allow / tau

    if result.safety_factor < 1.2:
        result.warnings.append("安全系数不足，建议增大线径或外径")

    # 最大变形量
    result.max_deflection = required_deflection * 1.5  # 1.5倍安全余量
    result.max_force = k * result.max_deflection

    # 自由长度
    solid_length = total_coils * d
    result.free_length = solid_length + result.max_deflection + 0.15 * result.max_deflection

    return result


@dataclass
class VacuumResult:
    """真空吸盘选型结果"""
    suction_cup_diameter: float = 0.0  # 吸盘直径 mm
    vacuum_pressure_kpa: float = 0.0   # 真空度 kPa
    holding_force_n: float = 0.0       # 理论吸力 N
    actual_holding_force: float = 0.0   # 实际吸力 N
    safety_factor: float = 0.0        # 安全系数
    recommended_size: str = ""         # 推荐规格
    warnings: list = field(default_factory=list)


def vacuum_cup_selection(
    payload_kg: float,
    number_of_cups: int = 1,
    vacuum_pressure_kpa: float = -60.0,
    horizontal_acceleration: float = 0.0,
    vertical_acceleration: float = 0.0,
    safety_factor: float = 2.0,
) -> VacuumResult:
    """
    真空吸盘选型计算

    Args:
        payload_kg: 负载质量 kg
        number_of_cups: 吸盘数量
        vacuum_pressure_kpa: 真空度 kPa (负压为负)
        horizontal_acceleration: 水平加速度 m/s²
        vertical_acceleration: 垂直加速度 m/s²
        safety_factor: 安全系数 (水平≥2, 垂直≥4)

    Returns:
        VacuumResult
    """
    result = VacuumResult()
    result.vacuum_pressure_kpa = abs(vacuum_pressure_kpa)

    g = 9.81

    # 计算实际所需吸力
    # 考虑加速度影响
    total_force = payload_kg * (g + abs(vertical_acceleration))
    if horizontal_acceleration > 0:
        # 水平力需要额外的摩擦系数
        friction_coeff = 0.5  # 橡胶-金属
        horizontal_force = payload_kg * horizontal_acceleration
        total_force += horizontal_force / friction_coeff

    # 每个吸盘需要的吸力
    required_per_cup = total_force * safety_factor / number_of_cups
    result.holding_force_n = required_per_cup

    # 吸盘面积: F = P * A
    # A = F / P (m²)
    area_per_cup = (required_per_cup) / (abs(vacuum_pressure_kpa) * 1000)  # m²

    # 换算成直径
    # A = π * d² / 4
    d_m = math.sqrt(4 * area_per_cup / math.pi)
    d_mm = d_m * 1000

    result.suction_cup_diameter = d_mm

    # 标准吸盘直径
    standard_sizes = [2, 4, 6, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 125, 150]
    for std_d in standard_sizes:
        if std_d >= d_mm:
            result.suction_cup_diameter = std_d
            break
    else:
        result.suction_cup_diameter = standard_sizes[-1]
        result.warnings.append("需要更大直径吸盘，建议增加吸盘数量")

    result.recommended_size = f"φ{result.suction_cup_diameter}"

    # 实际吸力
    actual_area = math.pi * (result.suction_cup_diameter / 1000)**2 / 4
    result.actual_holding_force = actual_area * abs(vacuum_pressure_kpa) * 1000 * number_of_cups

    # 安全系数
    total_payload_force = payload_kg * g
    result.safety_factor = result.actual_holding_force / (total_payload_force * number_of_cups) if total_payload_force > 0 else 999

    if result.safety_factor < safety_factor:
        result.warnings.append(f"安全系数不足，建议增大吸盘直径或数量")

    return result
