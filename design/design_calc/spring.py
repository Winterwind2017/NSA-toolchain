"""
弹簧设计计算

压缩弹簧/拉伸弹簧/扭转弹簧设计计算。
公式来源: 机械设计手册、GB/T 1239
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class SpringResult:
    """弹簧设计结果"""
    wire_dia_mm: float = 0.0           # 线径 mm
    outer_dia_mm: float = 0.0          # 外径 mm
    inner_dia_mm: float = 0.0           # 内径 mm
    effective_coils: float = 0.0         # 有效圈数
    free_length_mm: float = 0.0        # 自由长度 mm
    stiffness_n_mm: float = 0.0        # 刚度 N/mm
    max_deflection_mm: float = 0.0    # 最大变形量 mm
    shear_stress: float = 0.0          # 切应力 MPa
    safety_factor: float = 0.0
    warnings: List[str] = field(default_factory=list)


def compression_spring_design(
    load_n: float,
    deflection_mm: float,
    max_outer_dia_mm: float = 20.0,
    spring_material: str = "65Mn",
) -> SpringResult:
    """
    压缩弹簧设计计算
    
    Args:
        load_n: 工作载荷 N
        deflection_mm: 工作变形量 mm
        max_outer_dia_mm: 最大外径限制 mm
        spring_material: 弹簧材料
    
    Returns:
        SpringResult
    """
    result = SpringResult()
    
    # 材料许用切应力
    allowable_shear = {
        "65Mn": 480,
        "60Si2Mn": 720,
        "不锈钢304": 430,
    }.get(spring_material, 480)
    
    # 切变模量
    G = 79000  # MPa
    
    # 弹簧指数 C (推荐 4-10)
    C = 6
    
    # 初步选择线径
    # τ = K * 8 * F * D / (π * d²)
    # K = (4C-1)/(4C-4) + 0.615/C
    K = (4*C - 1) / (4*C - 4) + 0.615 / C
    
    # 假设中径 D
    D = max_outer_dia_mm * 0.8
    
    # 计算线径
    d = math.sqrt(K * 8 * load_n * D / (math.pi * allowable_shear * 0.5))
    d = round(d * 2) / 2  # 取标准值
    
    result.wire_dia_mm = d
    result.outer_dia_mm = D + d
    result.inner_dia_mm = D - d
    
    # 刚度计算
    # k = G * d⁴ / (8 * D³ * n)
    # 先估算圈数
    stiffness = load_n / deflection_mm
    
    # 有效圈数
    n = G * d**4 / (8 * D**3 * stiffness)
    n = round(n * 2) / 2
    
    result.effective_coils = n
    result.stiffness_n_mm = stiffness
    
    # 自由长度
    solid_length = (n + 2) * d  # 并紧长度
    result.free_length_mm = solid_length + deflection_mm * 1.5
    
    # 最大变形量
    result.max_deflection_mm = deflection_mm * 1.2
    
    # 切应力校核
    actual_shear = K * 8 * load_n * D / (math.pi * d**3)
    result.shear_stress = actual_shear
    result.safety_factor = allowable_shear / actual_shear
    
    if result.safety_factor < 1.5:
        result.warnings.append(
            f"强度不足，安全系数 {result.safety_factor:.2f} < 1.5"
        )
    
    return result


@dataclass
class TorsionSpringResult:
    """扭转弹簧设计结果"""
    wire_dia_mm: float = 0.0
    outer_dia_mm: float = 0.0
    coils: float = 0.0
    torque_nmm: float = 0.0
    angle_deg: float = 0.0
    stiffness_nmm_deg: float = 0.0
    warnings: List[str] = field(default_factory=list)


def torsion_spring_design(
    torque_nmm: float,
    angle_deg: float,
    max_outer_dia_mm: float = 20.0,
) -> TorsionSpringResult:
    """
    扭转弹簧设计计算
    
    Args:
        torque_nmm: 工作扭矩 N·mm
        angle_deg: 扭转角度 度
        max_outer_dia_mm: 最大外径 mm
    
    Returns:
        TorsionSpringResult
    """
    result = TorsionSpringResult()
    result.torque_nmm = torque_nmm
    result.angle_deg = angle_deg
    
    # 弹性模量
    E = 206000  # MPa
    
    # 初步选择线径
    d = math.cbrt(32 * torque_nmm / (math.pi * 800))
    d = round(d * 2) / 2
    
    # 中径
    D = max_outer_dia_mm * 0.8
    
    result.wire_dia_mm = d
    result.outer_dia_mm = D + d
    
    # 扭转刚度
    # k = E * d⁴ / (3667 * D * n)  (N·mm/度)
    stiffness = torque_nmm / angle_deg
    
    # 圈数
    n = E * d**4 / (3667 * D * stiffness)
    n = round(n)
    
    result.coils = n
    result.stiffness_nmm_deg = stiffness
    
    return result
