"""
特种材料强度计算

钛合金、铝合金、不锈钢、工程塑料等特种材料强度校核。
公式来源: 材料力学、材料设计手册
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SpecialMaterialResult:
    """特种材料强度校核结果"""
    material: str = ""                  # 材料名称
    yield_strength: float = 0.0        # 屈服强度 MPa
    tensile_strength: float = 0.0      # 抗拉强度 MPa
    elastic_modulus: float = 0.0       # 弹性模量 GPa
    density: float = 0.0               # 密度 g/cm³
    allowable_stress: float = 0.0      # 许用应力 MPa
    safety_factor: float = 0.0
    pass_strength: bool = False
    warnings: List[str] = field(default_factory=list)


# 特种材料性能数据库
SPECIAL_MATERIALS: Dict[str, Dict[str, float]] = {
    # 钛合金
    "TC4钛合金": {
        "yield": 830,
        "tensile": 950,
        "E": 110,
        "density": 4.51,
    },
    "TC11钛合金": {
        "yield": 850,
        "tensile": 1000,
        "E": 115,
        "density": 4.48,
    },
    
    # 铝合金
    "6061-T6铝合金": {
        "yield": 276,
        "tensile": 310,
        "E": 68.9,
        "density": 2.70,
    },
    "7075-T6铝合金": {
        "yield": 503,
        "tensile": 572,
        "E": 71.7,
        "density": 2.81,
    },
    "2024-T4铝合金": {
        "yield": 345,
        "tensile": 470,
        "E": 73.1,
        "density": 2.78,
    },
    
    # 不锈钢
    "304不锈钢": {
        "yield": 205,
        "tensile": 520,
        "E": 193,
        "density": 7.93,
    },
    "316L不锈钢": {
        "yield": 205,
        "tensile": 485,
        "E": 193,
        "density": 7.98,
    },
    "17-4PH不锈钢": {
        "yield": 725,
        "tensile": 930,
        "E": 196,
        "density": 7.80,
    },
    
    # 高温合金
    "Inconel 718": {
        "yield": 1034,
        "tensile": 1241,
        "E": 200,
        "density": 8.19,
    },
    
    # 工程塑料
    "PEEK": {
        "yield": 100,
        "tensile": 100,
        "E": 3.6,
        "density": 1.30,
    },
    "POM (赛钢)": {
        "yield": 70,
        "tensile": 70,
        "E": 2.8,
        "density": 1.41,
    },
    "PA66 (尼龙)": {
        "yield": 80,
        "tensile": 80,
        "E": 2.8,
        "density": 1.14,
    },
    "PTFE (聚四氟乙烯)": {
        "yield": 20,
        "tensile": 20,
        "E": 0.5,
        "density": 2.20,
    },
    
    # 碳纤维
    "碳纤维复合材料": {
        "yield": 600,
        "tensile": 600,
        "E": 70,
        "density": 1.60,
    },
}


def special_material_check(
    material: str,
    stress_mpa: float,
    safety_factor: float = 1.5,
) -> SpecialMaterialResult:
    """
    特种材料强度校核
    
    Args:
        material: 材料名称
        stress_mpa: 工作应力 MPa
        safety_factor: 安全系数
    
    Returns:
        SpecialMaterialResult
    """
    result = SpecialMaterialResult()
    result.material = material
    
    # 查询材料性能
    props = SPECIAL_MATERIALS.get(material)
    if props is None:
        result.warnings.append(f"未找到材料 {material} 的性能数据")
        return result
    
    result.yield_strength = props["yield"]
    result.tensile_strength = props["tensile"]
    result.elastic_modulus = props["E"]
    result.density = props["density"]
    
    # 许用应力
    result.allowable_stress = result.yield_strength / safety_factor
    
    # 校核
    result.safety_factor = result.yield_strength / stress_mpa
    result.pass_strength = result.safety_factor >= safety_factor
    
    if not result.pass_strength:
        result.warnings.append(
            f"强度不足，安全系数 {result.safety_factor:.2f} < {safety_factor}"
        )
    
    return result


@dataclass
class MaterialSelectionResult:
    """材料选型结果"""
    recommended_material: str = ""
    weight_comparison: float = 0.0      # 相对钢的重量比
    cost_level: str = ""               # 成本等级
    warnings: List[str] = field(default_factory=list)


def material_selection(
    required_strength_mpa: float,
    max_weight_kg: float = 0,
    environment: str = "normal",
) -> MaterialSelectionResult:
    """
    根据要求选择合适材料
    
    Args:
        required_strength_mpa: 要求强度 MPa
        max_weight_kg: 最大重量 kg (0 表示不限制)
        environment: 使用环境 (normal/corrosive/high_temp)
    
    Returns:
        MaterialSelectionResult
    """
    result = MaterialSelectionResult()
    
    # 按强度和环境推荐材料
    if required_strength_mpa <= 100:
        if environment == "corrosive":
            result.recommended_material = "304不锈钢"
            result.cost_level = "中"
        else:
            result.recommended_material = "6061-T6铝合金"
            result.cost_level = "低"
            result.weight_comparison = 0.34  # 比钢轻 66%
    
    elif required_strength_mpa <= 300:
        if environment == "corrosive":
            result.recommended_material = "316L不锈钢"
            result.cost_level = "中高"
        elif max_weight_kg > 0:
            result.recommended_material = "7075-T6铝合金"
            result.cost_level = "中"
            result.weight_comparison = 0.34
        else:
            result.recommended_material = "45钢"
            result.cost_level = "低"
    
    elif required_strength_mpa <= 600:
        if environment == "high_temp":
            result.recommended_material = "TC4钛合金"
            result.cost_level = "高"
            result.weight_comparison = 0.58
        else:
            result.recommended_material = "40Cr"
            result.cost_level = "中"
    
    else:
        result.recommended_material = "Inconel 718"
        result.cost_level = "极高"
        result.warnings.append("强度要求很高，建议选用高温合金")
    
    return result
