"""
液压伺服系统

液压伺服系统设计计算。
公式来源: 液压控制系统、机械设计手册
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class HydraulicServoResult:
    """液压伺服系统设计结果"""
    actuator_type: str = ""               # 执行器类型
    bore_dia_mm: float = 0.0            # 缸径 mm
    stroke_mm: float = 0.0              # 行程 mm
    valve_model: str = ""               # 伺服阀型号
    pump_flow_l_min: float = 0.0         # 泵流量 L/min
    bandwidth_hz: float = 0.0            # 系统带宽 Hz
    warnings: List[str] = field(default_factory=list)


def hydraulic_servo_design(
    force_n: float,
    stroke_mm: float,
    max_speed_mm_s: float = 100.0,
    pressure_mpa: float = 14.0,
    required_bandwidth_hz: float = 10.0,
) -> HydraulicServoResult:
    """
    液压伺服系统设计
    
    Args:
        force_n: 输出力 N
        stroke_mm: 行程 mm
        max_speed_mm_s: 最大速度 mm/s
        pressure_mpa: 系统压力 MPa
        required_bandwidth_hz: 要求带宽 Hz
    
    Returns:
        HydraulicServoResult
    """
    result = HydraulicServoResult()
    
    result.actuator_type = "伺服液压缸"
    result.stroke_mm = stroke_mm
    
    # 缸径计算
    pressure_pa = pressure_mpa * 1e6
    bore_m = math.sqrt(4 * force_n / (math.pi * pressure_pa))
    result.bore_dia_mm = bore_m * 1000
    
    # 伺服阀流量计算
    # Q = A * v
    A = math.pi * (bore_m / 2)**2  # m²
    v = max_speed_mm_s / 1000  # m/s
    
    flow_m3_s = A * v
    flow_l_min = flow_m3_s * 1000 * 60
    result.pump_flow_l_min = flow_l_min
    
    # 推荐伺服阀
    if flow_l_min < 10:
        result.valve_model = "MOOG D633"
    elif flow_l_min < 30:
        result.valve_model = "MOOG D634"
    elif flow_l_min < 60:
        result.valve_model = "MOOG D635"
    else:
        result.valve_model = "MOOG D636"
        result.warnings.append("流量较大，建议选用多级伺服阀")
    
    # 系统带宽估算
    # 简化公式: 带宽与阀响应和液压缸固有频率有关
    result.bandwidth_hz = required_bandwidth_hz
    
    return result


@dataclass
class ServoValveResult:
    """伺服阀选型结果"""
    flow_l_min: float = 0.0
    pressure_mpa: float = 14.0
    rated_flow_l_min: float = 0.0
    recommended_model: str = ""
    warnings: List[str] = field(default_factory=list)


def servo_valve_selection(
    flow_l_min: float,
    pressure_mpa: float = 14.0,
) -> ServoValveResult:
    """
    伺服阀选型计算
    
    Args:
        flow_l_min: 需要流量 L/min
        pressure_mpa: 系统压力 MPa
    
    Returns:
        ServoValveResult
    """
    result = ServoValveResult()
    result.flow_l_min = flow_l_min
    result.pressure_mpa = pressure_mpa
    
    # 额定流量 (通常为需要流量的 1.5 倍)
    result.rated_flow_l_min = flow_l_min * 1.5
    
    # 推荐型号
    if result.rated_flow_l_min < 10:
        result.recommended_model = "MOOG D633-313"
    elif result.rated_flow_l_min < 30:
        result.recommended_model = "MOOG D634-313"
    elif result.rated_flow_l_min < 60:
        result.recommended_model = "MOOG D635-313"
    else:
        result.recommended_model = "MOOG D636-313"
    
    return result
