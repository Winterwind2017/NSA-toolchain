"""
超高压液压系统

超高压液压系统设计计算 (31.5MPa以上)。
公式来源: 液压工程手册、超高压技术
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class UltraHighPressureResult:
    """超高压液压系统设计结果"""
    pressure_mpa: float = 70.0          # 工作压力 MPa
    flow_l_min: float = 0.0             # 流量 L/min
    bore_dia_mm: float = 0.0           # 缸径 mm
    wall_thickness_mm: float = 0.0     # 壁厚 mm
    pump_type: str = ""                 # 泵类型
    material: str = ""                  # 材料
    warnings: List[str] = field(default_factory=list)


def ultra_high_pressure_design(
    force_n: float,
    flow_l_min: float = 5.0,
    pressure_mpa: float = 70.0,
) -> UltraHighPressureResult:
    """
    超高压液压系统设计
    
    Args:
        force_n: 输出力 N
        flow_l_min: 流量 L/min
        pressure_mpa: 工作压力 MPa (31.5-100MPa)
    
    Returns:
        UltraHighPressureResult
    """
    result = UltraHighPressureResult()
    result.pressure_mpa = pressure_mpa
    result.flow_l_min = flow_l_min
    
    # 缸径计算
    pressure_pa = pressure_mpa * 1e6
    bore_m = math.sqrt(4 * force_n / (math.pi * pressure_pa))
    result.bore_dia_mm = bore_m * 1000
    
    # 壁厚计算 (超高压)
    # 厚壁筒公式: t = D/2 * (sqrt([σ]+P / [σ]-P) - 1)
    D = result.bore_dia_mm
    
    # 材料选择
    if pressure_mpa <= 70:
        result.material = "42CrMo (调质)"
        allowable_stress = 350  # MPa
    elif pressure_mpa <= 100:
        result.material = "35CrMo (调质)"
        allowable_stress = 400  # MPa
    else:
        result.material = "不锈钢 17-4PH"
        allowable_stress = 500  # MPa
        result.warnings.append("压力超过100MPa，需要特殊密封和材料")
    
    # 厚壁筒计算
    P = pressure_mpa
    t = D / 2 * (math.sqrt((allowable_stress + P) / (allowable_stress - P)) - 1)
    
    # 加安全系数
    t *= 1.5
    result.wall_thickness_mm = t
    
    # 泵类型
    if pressure_mpa <= 50:
        result.pump_type = "径向柱塞泵"
    elif pressure_mpa <= 100:
        result.pump_type = "超高压柱塞泵"
    else:
        result.pump_type = "增压器"
        result.warnings.append("超高压系统建议采用增压器方案")
    
    return result


@dataclass
class UltraHighSealResult:
    """超高压密封设计结果"""
    seal_type: str = ""
    material: str = ""
    pressure_mpa: float = 0.0
    leakage_rate: float = 0.0
    warnings: List[str] = field(default_factory=list)


def ultra_high_pressure_seal(
    pressure_mpa: float,
    shaft_dia_mm: float = 20.0,
) -> UltraHighSealResult:
    """
    超高压密封设计
    
    Args:
        pressure_mpa: 工作压力 MPa
        shaft_dia_mm: 轴径 mm
    
    Returns:
        UltraHighSealResult
    """
    result = UltraHighSealResult()
    result.pressure_mpa = pressure_mpa
    
    # 密封类型选择
    if pressure_mpa <= 31.5:
        result.seal_type = "组合密封 (格莱圈)"
        result.material = "NBR + 聚四氟乙烯"
    elif pressure_mpa <= 70:
        result.seal_type = "斯特封 (Stepseal)"
        result.material = "FKM + 聚四氟乙烯"
    elif pressure_mpa <= 100:
        result.seal_type = "金属密封"
        result.material = "不锈钢 + 铜垫"
        result.warnings.append("超高压密封建议采用金属密封")
    else:
        result.seal_type = "超高压专用密封"
        result.material = "PEEK + 金属背环"
        result.warnings.append("压力超过100MPa，需要定制密封件")
    
    # 泄漏率估算
    if pressure_mpa <= 31.5:
        result.leakage_rate = 0.1  # mL/min
    elif pressure_mpa <= 70:
        result.leakage_rate = 0.5
    else:
        result.leakage_rate = 2.0
    
    return result
