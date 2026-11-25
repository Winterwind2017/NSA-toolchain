"""
真空系统极限设计

高真空/超高真空系统设计计算。
公式来源: 真空设计手册、GB/T 标准
"""

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class HighVacuumResult:
    """高真空系统设计结果"""
    vacuum_level: str = ""               # 真空等级
    ultimate_pressure_pa: float = 0.0   # 极限压力 Pa
    pumping_speed_l_s: float = 0.0      # 抽速 L/s
    leakage_rate_pa_m3_s: float = 0.0    # 漏率 Pa·m³/s
    pumpdown_time_min: float = 0.0      # 抽气时间 min
    recommended_pump: str = ""           # 推荐泵
    warnings: List[str] = field(default_factory=list)


def high_vacuum_system_design(
    chamber_volume_l: float,
    target_pressure_pa: float = 1e-3,
    leakage_rate_pa_m3_s: float = 1e-6,
    pumpdown_time_min: float = 30.0,
) -> HighVacuumResult:
    """
    高真空系统设计
    
    Args:
        chamber_volume_l: 真空室容积 L
        target_pressure_pa: 目标压力 Pa
        leakage_rate_pa_m3_s: 允许漏率 Pa·m³/s
        pumpdown_time_min: 要求抽气时间 min
    
    Returns:
        HighVacuumResult
    """
    result = HighVacuumResult()
    
    # 真空等级判断
    if target_pressure_pa >= 1e5:
        result.vacuum_level = "低真空"
    elif target_pressure_pa >= 1e2:
        result.vacuum_level = "中真空"
    elif target_pressure_pa >= 1e-1:
        result.vacuum_level = "高真空"
    elif target_pressure_pa >= 1e-5:
        result.vacuum_level = "超高真空"
    else:
        result.vacuum_level = "极高真空"
    
    result.ultimate_pressure_pa = target_pressure_pa
    result.leakage_rate_pa_m3_s = leakage_rate_pa_m3_s
    
    # 所需抽速计算
    # S = V * ln(P0/Pt) / t + Q/Pt
    # 简化公式
    P0 = 1e5  # 初始压力 Pa
    Pt = target_pressure_pa
    t = pumpdown_time_min * 60  # s
    
    # 体积流量换算
    V_m3 = chamber_volume_l / 1000
    
    # 抽速计算
    pumping_speed = V_m3 * math.log(P0 / Pt) / t * 1000  # L/s
    result.pumping_speed_l_s = pumping_speed
    
    # 抽气时间
    result.pumpdown_time_min = pumpdown_time_min
    
    # 推荐真空泵
    if target_pressure_pa > 1e2:
        result.recommended_pump = "旋片式机械泵"
    elif target_pressure_pa > 1e-1:
        result.recommended_pump = "旋片泵 + 罗茨泵"
    elif target_pressure_pa > 1e-5:
        result.recommended_pump = "分子泵 + 机械泵"
    else:
        result.recommended_pump = "离子泵 + 钛升华泵"
        result.warnings.append("超高真空系统需要特殊材料和工艺")
    
    return result


@dataclass
class VacuumChamberResult:
    """真空室设计结果"""
    inner_dia_mm: float = 0.0
    wall_thickness_mm: float = 0.0
    flanges: List[str] = field(default_factory=list)
    material: str = "SUS304"
    warnings: List[str] = field(default_factory=list)


def vacuum_chamber_design(
    inner_dia_mm: float,
    height_mm: float,
    target_pressure_pa: float = 1e-3,
) -> VacuumChamberResult:
    """
    真空室设计 (壁厚计算)
    
    Args:
        inner_dia_mm: 内径 mm
        height_mm: 高度 mm
        target_pressure_pa: 目标压力 Pa
    
    Returns:
        VacuumChamberResult
    """
    result = VacuumChamberResult()
    result.inner_dia_mm = inner_dia_mm
    
    # 材料
    if target_pressure_pa < 1e-3:
        result.material = "SUS316L"
    else:
        result.material = "SUS304"
    
    # 壁厚计算 (外压容器)
    # t = P * D / (2 * [σ] * φ)
    P = 0.1  # 外压 MPa (大气压)
    D = inner_dia_mm
    
    # 许用应力 (不锈钢)
    allowable_stress = 137  # MPa
    
    # 焊接系数
    phi = 0.8
    
    wall_thickness = P * D / (2 * allowable_stress * phi)
    
    # 加腐蚀余量
    wall_thickness += 2
    
    result.wall_thickness_mm = wall_thickness
    
    # 推荐法兰
    result.flanges = ["CF法兰 (高真空)", "KF法兰 (低真空)"]
    
    if wall_thickness < 3:
        result.warnings.append("壁厚过薄，建议加强")
    
    return result
