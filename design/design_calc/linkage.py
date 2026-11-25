"""
连杆机构计算

四杆机构、曲柄滑块机构设计计算。
公式来源: 机械原理
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class FourBarResult:
    """四杆机构设计结果"""
    crank_length_mm: float = 0.0        # 曲柄长度 mm
    connecting_rod_mm: float = 0.0     # 连杆长度 mm
    rocker_length_mm: float = 0.0      # 摇杆长度 mm
    frame_length_mm: float = 0.0        # 机架长度 mm
    max_rocker_angle_deg: float = 0.0   # 最大摆角 度
    crank_rotatable: bool = False       # 曲柄是否可整周转动
    warnings: List[str] = field(default_factory=list)


def four_bar_design(
    rocker_angle_deg: float,
    rocker_length_mm: float = 50.0,
    frame_length_mm: float = 100.0,
) -> FourBarResult:
    """
    四杆机构设计 (按摇杆摆角设计)
    
    Args:
        rocker_angle_deg: 摇杆摆角 度
        rocker_length_mm: 摇杆长度 mm
        frame_length_mm: 机架长度 mm
    
    Returns:
        FourBarResult
    """
    result = FourBarResult()
    
    result.rocker_length_mm = rocker_length_mm
    result.frame_length_mm = frame_length_mm
    result.max_rocker_angle_deg = rocker_angle_deg
    
    # 简化设计: 曲柄摇杆机构
    # 按行程速比系数 K 设计
    K = 1.2  # 一般取 1.2-1.5
    
    # 极位夹角
    theta = 180 * (K - 1) / (K + 1)
    
    # 曲柄和连杆长度 (简化)
    a = frame_length_mm * 0.2
    b = frame_length_mm * 0.8
    
    result.crank_length_mm = a
    result.connecting_rod_mm = b
    
    # 格拉霍夫定理: 最短杆 + 最长杆 <= 其余两杆之和
    lengths = sorted([a, b, rocker_length_mm, frame_length_mm])
    result.crank_rotatable = (lengths[0] + lengths[3]) <= (lengths[1] + lengths[2])
    
    if not result.crank_rotatable:
        result.warnings.append("不满足格拉霍夫定理，曲柄不能整周转动")
    
    return result


@dataclass
class CrankSliderResult:
    """曲柄滑块机构设计结果"""
    crank_length_mm: float = 0.0
    connecting_rod_mm: float = 0.0
    stroke_mm: float = 0.0
    max_velocity_mm_s: float = 0.0
    max_acceleration_mm_s2: float = 0.0
    warnings: List[str] = field(default_factory=list)


def crank_slider_design(
    stroke_mm: float,
    crank_speed_rpm: float = 60.0,
    ratio: float = 3.0,
) -> CrankSliderResult:
    """
    曲柄滑块机构设计
    
    Args:
        stroke_mm: 行程 mm
        crank_speed_rpm: 曲柄转速 rpm
        ratio: 连杆/曲柄比 (推荐 3-5)
    
    Returns:
        CrankSliderResult
    """
    result = CrankSliderResult()
    
    # 行程 = 2 * 曲柄长度
    crank_radius = stroke_mm / 2
    result.crank_length_mm = crank_radius
    result.stroke_mm = stroke_mm
    
    # 连杆长度
    result.connecting_rod_mm = crank_radius * ratio
    
    # 最大速度 (简化)
    # v_max = ω * r
    omega = 2 * math.pi * crank_speed_rpm / 60  # rad/s
    v_max = omega * crank_radius * 1000  # mm/s
    result.max_velocity_mm_s = v_max
    
    # 最大加速度 (简化)
    # a_max = ω² * r * (1 + 1/λ)
    # λ = r/l
    lamda = crank_radius / result.connecting_rod_mm
    a_max = omega**2 * crank_radius * (1 + lamda) * 1000  # mm/s²
    result.max_acceleration_mm_s2 = a_max
    
    return result
