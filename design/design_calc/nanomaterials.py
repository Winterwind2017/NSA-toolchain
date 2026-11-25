"""
纳米材料强度计算

纳米材料、二维材料、纳米结构强度计算。
公式来源: 纳米材料力学、材料科学基础
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class NanoMaterialResult:
    """纳米材料强度计算结果"""
    material: str = ""
    youngs_modulus_gpa: float = 0.0      # 弹性模量 GPa
    tensile_strength_gpa: float = 0.0     # 抗拉强度 GPa
    density_g_cm3: float = 0.0           # 密度 g/cm³
    specific_strength: float = 0.0         # 比强度
    warnings: List[str] = field(default_factory=list)


# 纳米材料性能数据库
NANO_MATERIALS: Dict[str, Dict[str, float]] = {
    # 碳纳米材料
    "石墨烯": {
        "E": 1000,
        "strength": 130,
        "density": 2.27,
    },
    "碳纳米管 (单壁)": {
        "E": 1000,
        "strength": 50,
        "density": 1.3,
    },
    "碳纳米管 (多壁)": {
        "E": 900,
        "strength": 20,
        "density": 1.8,
    },
    
    # 二维材料
    "二硫化钼 (MoS2)": {
        "E": 270,
        "strength": 23,
        "density": 5.06,
    },
    "六方氮化硼 (h-BN)": {
        "E": 800,
        "strength": 70,
        "density": 2.1,
    },
    
    # 纳米晶材料
    "纳米晶铜": {
        "E": 110,
        "strength": 0.4,
        "density": 8.96,
    },
    "纳米晶镍": {
        "E": 200,
        "strength": 1.5,
        "density": 8.9,
    },
    
    # 纳米复合材料
    "碳纤维增强复合材料": {
        "E": 150,
        "strength": 2.0,
        "density": 1.6,
    },
    "碳纳米管增强复合材料": {
        "E": 200,
        "strength": 3.0,
        "density": 1.5,
    },
}


def nano_material_properties(
    material: str,
) -> NanoMaterialResult:
    """
    纳米材料性能查询
    
    Args:
        material: 材料名称
    
    Returns:
        NanoMaterialResult
    """
    result = NanoMaterialResult()
    result.material = material
    
    props = NANO_MATERIALS.get(material)
    if props is None:
        result.warnings.append(f"未找到材料 {material} 的性能数据")
        return result
    
    result.youngs_modulus_gpa = props["E"]
    result.tensile_strength_gpa = props["strength"]
    result.density_g_cm3 = props["density"]
    
    # 比强度 (强度/密度)
    result.specific_strength = result.tensile_strength_gpa / result.density_g_cm3
    
    return result


@dataclass
class NanoCompositeResult:
    """纳米复合材料性能计算结果"""
    matrix_material: str = ""
    nano_filler: str = ""
    filler_volume_fraction: float = 0.0    # 填料体积分数 %
    composite_E_gpa: float = 0.0           # 复合后弹性模量 GPa
    composite_strength_gpa: float = 0.0    # 复合后抗拉强度 GPa
    warnings: List[str] = field(default_factory=list)


def nano_composite_calculation(
    matrix_material: str = "epoxy",
    nano_filler: str = "石墨烯",
    filler_volume_fraction: float = 5.0,
) -> NanoCompositeResult:
    """
    纳米复合材料性能估算 (混合定律)
    
    Args:
        matrix_material: 基体材料
        nano_filler: 纳米填料
        filler_volume_fraction: 填料体积分数 %
    
    Returns:
        NanoCompositeResult
    """
    result = NanoCompositeResult()
    result.matrix_material = matrix_material
    result.nano_filler = nano_filler
    result.filler_volume_fraction = filler_volume_fraction
    
    # 基体性能 (环氧树脂)
    matrix_E = 3.5  # GPa
    matrix_strength = 0.07  # GPa
    
    # 填料性能
    filler_props = NANO_MATERIALS.get(nano_filler)
    if filler_props is None:
        result.warnings.append(f"未找到填料 {nano_filler} 的性能数据")
        return result
    
    filler_E = filler_props["E"]
    filler_strength = filler_props["strength"]
    
    # 混合定律 (Voigt模型)
    Vf = filler_volume_fraction / 100
    Vm = 1 - Vf
    
    # 弹性模量
    composite_E = Vm * matrix_E + Vf * filler_E
    
    # 强度 (简化估算)
    composite_strength = Vm * matrix_strength + Vf * filler_strength * 0.1  # 10% 效率
    
    result.composite_E_gpa = composite_E
    result.composite_strength_gpa = composite_strength
    
    return result
