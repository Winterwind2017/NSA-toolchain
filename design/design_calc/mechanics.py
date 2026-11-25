"""
材料力学计算

梁强度、柱稳定性、螺栓强度、焊缝强度、轴强度校核。
公式来源: 材料力学、机械设计手册
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class BeamResult:
    """梁强度校核结果"""
    max_bending_stress: float = 0.0      # 最大弯曲应力 MPa
    allowable_stress: float = 0.0       # 许用应力 MPa
    safety_factor: float = 0.0          # 安全系数
    max_deflection: float = 0.0         # 最大挠度 mm
    allowable_deflection: float = 0.0   # 许用挠度 mm
    pass_strength: bool = False          # 强度是否通过
    pass_stiffness: bool = False        # 刚度是否通过
    warnings: List[str] = field(default_factory=list)


def beam_bending_check(
    load_n: float,
    span_mm: float,
    width_mm: float,
    height_mm: float,
    material: str = "6061铝",
    support_type: str = "simply",
) -> BeamResult:
    """
    梁弯曲强度校核
    
    Args:
        load_n: 集中载荷 N
        span_mm: 跨度 mm
        width_mm: 梁宽 mm
        height_mm: 梁高 mm
        material: 材料
        support_type: 支撑类型 (simply/cantilever)
    
    Returns:
        BeamResult
    """
    result = BeamResult()
    
    # 材料许用应力
    allowable_stress = {
        "6061铝": 100,
        "45钢": 200,
        "Q235钢": 120,
        "304不锈钢": 150,
    }.get(material, 100)
    result.allowable_stress = allowable_stress
    
    # 材料弹性模量
    E = {
        "6061铝": 68900,
        "45钢": 209000,
        "Q235钢": 210000,
        "304不锈钢": 193000,
    }.get(material, 68900)
    
    L = span_mm
    b = width_mm
    h = height_mm
    
    # 截面惯性矩
    I = b * h**3 / 12
    
    # 截面系数
    W = b * h**2 / 6
    
    # 弯矩计算
    if support_type == "cantilever":
        # 悬臂梁
        M = load_n * L
        # 挠度 δ = F*L³ / (3*E*I)
        deflection = load_n * L**3 / (3 * E * I)
    else:
        # 简支梁 (中点受载)
        M = load_n * L / 4
        # 挠度 δ = F*L³ / (48*E*I)
        deflection = load_n * L**3 / (48 * E * I)
    
    # 弯曲应力
    bending_stress = M / W  # MPa (因为 N/mm² = MPa)
    result.max_bending_stress = bending_stress
    
    # 安全系数
    result.safety_factor = allowable_stress / bending_stress
    
    # 强度校核
    result.pass_strength = result.safety_factor >= 1.5
    
    # 挠度
    result.max_deflection = deflection
    
    # 许用挠度 (L/250)
    result.allowable_deflection = L / 250
    
    # 刚度校核
    result.pass_stiffness = deflection <= result.allowable_deflection
    
    if not result.pass_strength:
        result.warnings.append(f"强度不足，安全系数 {result.safety_factor:.2f} < 1.5")
    
    if not result.pass_stiffness:
        result.warnings.append(
            f"刚度不足，挠度 {deflection:.2f}mm > 许用 {result.allowable_deflection:.2f}mm"
        )
    
    return result


@dataclass
class ColumnResult:
    """压杆稳定校核结果"""
    slenderness_ratio: float = 0.0       # 长细比
    critical_stress: float = 0.0        # 临界应力 MPa
    actual_stress: float = 0.0          # 实际应力 MPa
    stability_safety: float = 0.0       # 稳定安全系数
    pass_stability: bool = False
    warnings: List[str] = field(default_factory=list)


def column_stability_check(
    axial_load_n: float,
    length_mm: float,
    diameter_mm: float,
    material: str = "45钢",
    end_condition: str = "both_fixed",
) -> ColumnResult:
    """
    压杆稳定校核 (欧拉公式)
    
    Args:
        axial_load_n: 轴向压力 N
        length_mm: 杆长 mm
        diameter_mm: 直径 mm
        material: 材料
        end_condition: 端部条件
    
    Returns:
        ColumnResult
    """
    result = ColumnResult()
    
    # 弹性模量
    E = {
        "6061铝": 68900,
        "45钢": 209000,
        "Q235钢": 210000,
    }.get(material, 209000)
    
    # 长度系数
    mu = {
        "both_fixed": 0.5,
        "one_fixed_one_pinned": 0.7,
        "both_pinned": 1.0,
        "one_fixed_one_free": 2.0,
    }.get(end_condition, 1.0)
    
    L = length_mm
    d = diameter_mm
    
    # 截面面积
    A = math.pi * d**2 / 4
    
    # 惯性半径
    i = d / 4
    
    # 长细比
    slenderness = mu * L / i
    result.slenderness_ratio = slenderness
    
    # 临界应力 (欧拉公式)
    # σ_cr = π²E / λ²
    critical_stress = math.pi**2 * E / slenderness**2
    result.critical_stress = critical_stress
    
    # 实际应力
    actual_stress = axial_load_n / A
    result.actual_stress = actual_stress
    
    # 稳定安全系数
    stability_safety = critical_stress / actual_stress
    result.stability_safety = stability_safety
    
    # 校核 (安全系数 ≥ 3)
    result.pass_stability = stability_safety >= 3.0
    
    if not result.pass_stability:
        result.warnings.append(
            f"稳定安全系数 {stability_safety:.2f} < 3.0，建议增大直径"
        )
    
    return result


@dataclass
class BoltResult:
    """螺栓强度校核结果"""
    tensile_stress: float = 0.0         # 拉应力 MPa
    shear_stress: float = 0.0           # 剪应力 MPa
    equivalent_stress: float = 0.0      # 当量应力 MPa
    allowable_stress: float = 0.0       # 许用应力 MPa
    safety_factor: float = 0.0
    pass_strength: bool = False
    warnings: List[str] = field(default_factory=list)


def bolt_strength_check(
    bolt_dia_mm: float,
    tensile_force_n: float = 0.0,
    shear_force_n: float = 0.0,
    bolt_grade: str = "8.8",
) -> BoltResult:
    """
    螺栓强度校核
    
    Args:
        bolt_dia_mm: 螺栓直径 mm
        tensile_force_n: 拉力 N
        shear_force_n: 剪力 N
        bolt_grade: 螺栓等级 (4.8/8.8/10.9)
    
    Returns:
        BoltResult
    """
    result = BoltResult()
    
    # 螺栓许用应力
    yield_strength = {
        "4.8": 320,
        "8.8": 640,
        "10.9": 900,
    }.get(bolt_grade, 640)
    
    # 安全系数 1.5
    result.allowable_stress = yield_strength / 1.5
    
    d = bolt_dia_mm
    
    # 应力面积 (简化)
    A = math.pi * d**2 / 4
    
    # 拉应力
    if tensile_force_n > 0:
        result.tensile_stress = tensile_force_n / A
    
    # 剪应力
    if shear_force_n > 0:
        result.shear_stress = shear_force_n / A
    
    # 当量应力 (第四强度理论)
    result.equivalent_stress = math.sqrt(
        result.tensile_stress**2 + 3 * result.shear_stress**2
    )
    
    # 安全系数
    if result.equivalent_stress > 0:
        result.safety_factor = result.allowable_stress / result.equivalent_stress
    
    # 校核
    result.pass_strength = result.safety_factor >= 1.5
    
    if not result.pass_strength and result.equivalent_stress > 0:
        result.warnings.append(
            f"强度不足，安全系数 {result.safety_factor:.2f} < 1.5"
        )
    
    return result


@dataclass
class WeldResult:
    """焊缝强度校核结果"""
    weld_shear_stress: float = 0.0      # 焊缝剪应力 MPa
    allowable_shear: float = 0.0        # 许用剪应力 MPa
    safety_factor: float = 0.0
    pass_strength: bool = False
    warnings: List[str] = field(default_factory=list)


def weld_strength_check(
    weld_length_mm: float,
    weld_throat_mm: float,
    shear_force_n: float,
    weld_material: str = "E43",
) -> WeldResult:
    """
    焊缝强度校核
    
    Args:
        weld_length_mm: 焊缝长度 mm
        weld_throat_mm: 焊缝焊喉厚度 mm
        shear_force_n: 剪力 N
        weld_material: 焊条型号
    
    Returns:
        WeldResult
    """
    result = WeldResult()
    
    # 焊缝许用剪应力
    allowable_shear = {
        "E43": 113,
        "E50": 148,
    }.get(weld_material, 113)
    result.allowable_shear = allowable_shear
    
    # 焊缝受剪面积
    A = weld_length_mm * weld_throat_mm
    
    # 剪应力
    result.weld_shear_stress = shear_force_n / A
    
    # 安全系数
    result.safety_factor = allowable_shear / result.weld_shear_stress
    
    # 校核
    result.pass_strength = result.safety_factor >= 1.5
    
    if not result.pass_strength:
        result.warnings.append(
            f"焊缝强度不足，安全系数 {result.safety_factor:.2f} < 1.5"
        )
    
    return result
