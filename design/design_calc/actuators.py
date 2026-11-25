"""
电动缸/液压缸/凸轮机构/人机工程

电动缸选型、液压缸计算、凸轮机构、人机工程学计算。
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ElectricCylinderResult:
    """电动缸选型结果"""
    thrust_n: float = 0.0               # 推力 N
    stroke_mm: float = 0.0             # 行程 mm
    speed_mm_s: float = 0.0            # 速度 mm/s
    recommended_model: str = ""         # 推荐型号
    warnings: List[str] = field(default_factory=list)


def electric_cylinder_selection(
    thrust_n: float,
    stroke_mm: float,
    speed_mm_s: float = 100.0,
) -> ElectricCylinderResult:
    """
    电动缸选型计算
    
    Args:
        thrust_n: 推力 N
        stroke_mm: 行程 mm
        speed_mm_s: 速度 mm/s
    
    Returns:
        ElectricCylinderResult
    """
    result = ElectricCylinderResult()
    result.thrust_n = thrust_n
    result.stroke_mm = stroke_mm
    result.speed_mm_s = speed_mm_s
    
    # 推荐型号 (按推力)
    if thrust_n < 100:
        result.recommended_model = "IAI RCP2"
    elif thrust_n < 500:
        result.recommended_model = "IAI RCP4"
    elif thrust_n < 1500:
        result.recommended_model = "IAI RCS2"
    elif thrust_n < 3000:
        result.recommended_model = "IAI RCS3"
    else:
        result.recommended_model = "电动推杆"
        result.warnings.append("推力较大，建议选用液压系统")
    
    return result


@dataclass
class HydraulicCylinderResult:
    """液压缸计算结果"""
    bore_dia_mm: float = 0.0
    rod_dia_mm: float = 0.0
    stroke_mm: float = 0.0
    pressure_mpa: float = 7.0
    thrust_n: float = 0.0
    warnings: List[str] = field(default_factory=list)


def hydraulic_cylinder_calculation(
    thrust_n: float,
    stroke_mm: float,
    pressure_mpa: float = 7.0,
) -> HydraulicCylinderResult:
    """
    液压缸计算
    
    Args:
        thrust_n: 推力 N
        stroke_mm: 行程 mm
        pressure_mpa: 工作压力 MPa
    
    Returns:
        HydraulicCylinderResult
    """
    result = HydraulicCylinderResult()
    result.thrust_n = thrust_n
    result.stroke_mm = stroke_mm
    result.pressure_mpa = pressure_mpa
    
    # 缸径计算
    # F = P * A = P * π * d² / 4
    pressure_pa = pressure_mpa * 1e6
    bore_m = math.sqrt(4 * thrust_n / (math.pi * pressure_pa))
    result.bore_dia_mm = bore_m * 1000
    
    # 杆径 (通常为缸径的 0.5-0.7)
    result.rod_dia_mm = result.bore_dia_mm * 0.6
    
    return result


@dataclass
class CamResult:
    """凸轮机构设计结果"""
    base_circle_mm: float = 0.0        # 基圆半径 mm
    roller_dia_mm: float = 0.0          # 滚子直径 mm
    lift_mm: float = 0.0                # 升程 mm
    max_pressure_angle_deg: float = 0.0  # 最大压力角 度
    warnings: List[str] = field(default_factory=list)


def cam_design(
    lift_mm: float,
    speed_rpm: float = 60.0,
) -> CamResult:
    """
    凸轮机构设计 (简化)
    
    Args:
        lift_mm: 升程 mm
        speed_rpm: 转速 rpm
    
    Returns:
        CamResult
    """
    result = CamResult()
    result.lift_mm = lift_mm
    
    # 基圆半径 (通常为升程的 5-10 倍)
    result.base_circle_mm = lift_mm * 8
    
    # 滚子直径
    result.roller_dia_mm = lift_mm * 0.5
    
    # 最大压力角 (推荐 < 30 度)
    result.max_pressure_angle_deg = 30.0
    
    if speed_rpm > 300:
        result.warnings.append("转速较高，建议增大基圆半径")
    
    return result


@dataclass
class ErgonomicsResult:
    """人机工程计算结果"""
    operation_height_mm: float = 0.0    # 操作高度 mm
    reach_range_mm: float = 0.0        # 伸手可达范围 mm
    view_height_mm: float = 0.0         # 视觉高度 mm
    warnings: List[str] = field(default_factory=list)


def ergonomics_calculation(
    operator_height_mm: float = 1700.0,
) -> ErgonomicsResult:
    """
    人机工程学计算
    
    Args:
        operator_height_mm: 操作人员身高 mm
    
    Returns:
        ErgonomicsResult
    """
    result = ErgonomicsResult()
    
    # 操作高度 (肘部高度，约为身高的 0.6)
    result.operation_height_mm = operator_height_mm * 0.6
    
    # 伸手可达范围 (约为身高的 1.5 倍)
    result.reach_range_mm = operator_height_mm * 1.5
    
    # 视觉高度 (眼睛高度，约为身高的 0.93)
    result.view_height_mm = operator_height_mm * 0.93
    
    return result
