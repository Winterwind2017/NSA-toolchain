"""
热工计算

轴承温升、电机发热、散热计算。
公式来源: 机械设计手册、热工基础
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class BearingTempResult:
    """轴承温升计算结果"""
    heat_generation_w: float = 0.0     # 发热量 W
    temperature_rise: float = 0.0      # 温升 ℃
    max_allowable_temp: float = 80.0   # 最高允许温度 ℃
    temp_ok: bool = False
    warnings: List[str] = field(default_factory=list)


def bearing_temperature_calculation(
    load_n: float,
    speed_rpm: float,
    bearing_type: str = "ball",
) -> BearingTempResult:
    """
    轴承温升计算
    
    Args:
        load_n: 轴承载荷 N
        speed_rpm: 转速 rpm
        bearing_type: 轴承类型 (ball/roller)
    
    Returns:
        BearingTempResult
    """
    result = BearingTempResult()
    
    # 摩擦系数
    mu = {
        "ball": 0.0015,
        "roller": 0.002,
    }.get(bearing_type, 0.0015)
    
    # 发热量计算
    # Q = μ * P * v / 1000
    # v = π * d * n / 60000 (m/s)
    # 这里用简化公式
    heat = mu * load_n * speed_rpm / 10000
    result.heat_generation_w = heat
    
    # 温升估算 (简化)
    # ΔT = Q / (h * A)
    # 假设散热系数 h = 10 W/m²·℃
    temp_rise = heat * 10  # 经验值
    result.temperature_rise = temp_rise
    
    # 校核 (假设环境温度 25℃)
    total_temp = 25 + temp_rise
    result.temp_ok = total_temp <= result.max_allowable_temp
    
    if not result.temp_ok:
        result.warnings.append(
            f"轴承温度 {total_temp:.0f}℃ 超过允许值 {result.max_allowable_temp}℃"
        )
    
    return result


@dataclass
class MotorHeatResult:
    """电机发热计算结果"""
    motor_power_kw: float = 0.0
    efficiency: float = 0.9
    heat_loss_kw: float = 0.0
    temperature_rise: float = 0.0
    warnings: List[str] = field(default_factory=list)


def motor_heat_calculation(
    motor_power_kw: float,
    efficiency: float = 0.9,
    load_ratio: float = 0.8,
) -> MotorHeatResult:
    """
    电机发热计算
    
    Args:
        motor_power_kw: 电机额定功率 kW
        efficiency: 电机效率
        load_ratio: 负载率
    
    Returns:
        MotorHeatResult
    """
    result = MotorHeatResult()
    result.motor_power_kw = motor_power_kw
    result.efficiency = efficiency
    
    # 实际输出功率
    actual_power = motor_power_kw * load_ratio
    
    # 损耗功率 (发热)
    # P_loss = P_in - P_out = P_out/η - P_out
    heat_loss = actual_power / efficiency - actual_power
    result.heat_loss_kw = heat_loss
    
    # 温升估算
    # 温升与功率和散热面积有关
    temp_rise = heat_loss * 100  # 经验值
    result.temperature_rise = temp_rise
    
    return result


@dataclass
class HeatSinkResult:
    """散热片计算结果"""
    heat_w: float = 0.0
    required_area_m2: float = 0.0
    fin_length_mm: float = 0.0
    warnings: List[str] = field(default_factory=list)


def heat_sink_calculation(
    heat_w: float,
    max_temp_rise: float = 20.0,
    ambient_temp: float = 25.0,
) -> HeatSinkResult:
    """
    散热片计算
    
    Args:
        heat_w: 发热量 W
        max_temp_rise: 最大允许温升 ℃
        ambient_temp: 环境温度 ℃
    
    Returns:
        HeatSinkResult
    """
    result = HeatSinkResult()
    result.heat_w = heat_w
    
    # 所需散热面积
    # Q = h * A * ΔT
    # A = Q / (h * ΔT)
    h = 10  # 自然对流散热系数 W/m²·℃
    required_area = heat_w / (h * max_temp_rise)
    result.required_area_m2 = required_area
    
    # 散热片长度估算 (假设宽度 100mm)
    width_m = 0.1
    length_m = required_area / width_m
    result.fin_length_mm = length_m * 1000
    
    return result
