"""
液压系统详细设计

液压泵、液压阀、油箱详细设计计算。
公式来源: 液压传动手册
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class HydraulicPumpResult:
    """液压泵选型结果"""
    flow_l_min: float = 0.0             # 流量 L/min
    pressure_mpa: float = 7.0           # 压力 MPa
    power_kw: float = 0.0               # 电机功率 kW
    recommended_model: str = ""
    warnings: List[str] = field(default_factory=list)


def hydraulic_pump_selection(
    flow_l_min: float,
    pressure_mpa: float = 7.0,
    efficiency: float = 0.85,
) -> HydraulicPumpResult:
    """
    液压泵选型计算
    
    Args:
        flow_l_min: 系统流量 L/min
        pressure_mpa: 工作压力 MPa
        efficiency: 泵效率
    
    Returns:
        HydraulicPumpResult
    """
    result = HydraulicPumpResult()
    result.flow_l_min = flow_l_min
    result.pressure_mpa = pressure_mpa
    
    # 电机功率计算
    # P = P * Q / (600 * η)  (kW)
    power = pressure_mpa * flow_l_min / (600 * efficiency)
    result.power_kw = power
    
    # 推荐型号
    if pressure_mpa <= 7:
        if flow_l_min < 10:
            result.recommended_model = "齿轮泵 CB-B10"
        elif flow_l_min < 25:
            result.recommended_model = "齿轮泵 CB-B25"
        elif flow_l_min < 63:
            result.recommended_model = "叶片泵 YB-63"
        else:
            result.recommended_model = "柱塞泵"
            result.warnings.append("流量较大，建议选用柱塞泵")
    else:
        result.recommended_model = "柱塞泵"
        result.warnings.append("压力较高，建议选用柱塞泵")
    
    return result


@dataclass
class OilTankResult:
    """油箱设计结果"""
    tank_volume_l: float = 0.0           # 油箱容积 L
    recommended_size: str = ""
    warnings: List[str] = field(default_factory=list)


def oil_tank_calculation(
    pump_flow_l_min: float,
    working_pressure_mpa: float = 7.0,
) -> OilTankResult:
    """
    油箱容积计算
    
    Args:
        pump_flow_l_min: 泵流量 L/min
        working_pressure_mpa: 工作压力 MPa
    
    Returns:
        OilTankResult
    """
    result = OilTankResult()
    
    # 油箱容积通常为泵流量的 2-5 倍
    # 低压取 2-3 倍，高压取 3-5 倍
    if working_pressure_mpa <= 7:
        multiplier = 3
    elif working_pressure_mpa <= 16:
        multiplier = 4
    else:
        multiplier = 5
    
    tank_volume = pump_flow_l_min * multiplier
    result.tank_volume_l = tank_volume
    
    # 推荐规格
    standard_tanks = [40, 63, 100, 160, 250, 400, 630]
    for size in standard_tanks:
        if size >= tank_volume:
            result.recommended_size = f"{size}L"
            break
    
    return result


@dataclass
class LubricationResult:
    """润滑系统计算结果"""
    lubrication_type: str = ""          # 润滑类型
    oil_viscosity: float = 0.0          # 油液粘度 cSt
    recommended_grease: str = ""        # 推荐润滑脂
    warnings: List[str] = field(default_factory=list)


def lubrication_selection(
    speed_rpm: float,
    load_type: str = "medium",
    environment: str = "normal",
) -> LubricationResult:
    """
    润滑方式与润滑脂选择
    
    Args:
        speed_rpm: 转速 rpm
        load_type: 载荷类型 (light/medium/heavy)
        environment: 环境 (normal/dusty/wet)
    
    Returns:
        LubricationResult
    """
    result = LubricationResult()
    
    # 润滑类型
    if speed_rpm < 100:
        result.lubrication_type = "脂润滑"
    elif speed_rpm < 1000:
        result.lubrication_type = "油浴润滑"
    else:
        result.lubrication_type = "循环油润滑"
    
    # 油液粘度选择
    if speed_rpm < 500:
        result.oil_viscosity = 68
    elif speed_rpm < 1500:
        result.oil_viscosity = 46
    else:
        result.oil_viscosity = 32
    
    # 载荷调整粘度
    if load_type == "heavy":
        result.oil_viscosity *= 1.5
    
    # 推荐润滑脂
    if environment == "dusty":
        result.recommended_grease = "锂基脂 2号 (防尘型)"
    elif environment == "wet":
        result.recommended_grease = "铝基脂 (防水型)"
    else:
        result.recommended_grease = "锂基脂 2号"
    
    return result
