"""
气源处理件选型计算

过滤器、减压阀、油雾器 (FRL) 选型计算。
公式来源: SMC/费斯托选型手册
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class AirTreatmentResult:
    """气源处理件选型结果"""
    flow_l_min: float = 0.0
    port_size: str = ""                  # 接口尺寸
    filter_model: str = ""               # 过滤器型号
    regulator_model: str = ""            # 减压阀型号
    recommended_model: str = ""          # 组合件型号
    warnings: List[str] = field(default_factory=list)


def air_treatment_selection(
    total_flow_l_min: float,
    pressure_mpa: float = 0.5,
) -> AirTreatmentResult:
    """
    气源处理件选型计算 (FRL 三联件)
    
    Args:
        total_flow_l_min: 总耗气量 L/min
        pressure_mpa: 工作压力 MPa
    
    Returns:
        AirTreatmentResult
    """
    result = AirTreatmentResult()
    result.flow_l_min = total_flow_l_min
    
    # 选择接口尺寸
    if total_flow_l_min < 500:
        result.port_size = "1/8\""
        result.recommended_model = "SMC AC20A-01"
    elif total_flow_l_min < 2000:
        result.port_size = "1/4\""
        result.recommended_model = "SMC AC30A-02"
    elif total_flow_l_min < 5000:
        result.port_size = "3/8\""
        result.recommended_model = "SMC AC40A-03"
    elif total_flow_l_min < 10000:
        result.port_size = "1/2\""
        result.recommended_model = "SMC AC50A-04"
    else:
        result.port_size = "1\""
        result.recommended_model = "SMC AC60A-06"
        result.warnings.append("流量较大，建议选用更大口径或多联件")
    
    # 分别型号
    result.filter_model = result.recommended_model.replace("AC", "AF")
    result.regulator_model = result.recommended_model.replace("AC", "AR")
    
    return result


@dataclass
class RelayResult:
    """继电器选型结果"""
    load_voltage_v: float = 0.0
    load_current_a: float = 0.0
    contact_type: str = ""               # 触点类型
    recommended_model: str = ""          # 推荐型号
    warnings: List[str] = field(default_factory=list)


def relay_selection(
    load_voltage_v: float,
    load_current_a: float,
    contact_type: str = "no",
) -> RelayResult:
    """
    继电器选型计算
    
    Args:
        load_voltage_v: 负载电压 V
        load_current_a: 负载电流 A
        contact_type: 触点类型 (no/nc/com)
    
    Returns:
        RelayResult
    """
    result = RelayResult()
    result.load_voltage_v = load_voltage_v
    result.load_current_a = load_current_a
    
    # 触点类型
    contact_names = {
        "no": "常开",
        "nc": "常闭",
        "com": "转换",
    }
    result.contact_type = contact_names.get(contact_type, "常开")
    
    # 推荐型号
    if load_current_a < 2:
        result.recommended_model = "欧姆龙 MY2N-J DC24"
    elif load_current_a < 5:
        result.recommended_model = "欧姆龙 MY4N-J DC24"
    elif load_current_a < 10:
        result.recommended_model = "欧姆龙 LY2N-J DC24"
    else:
        result.recommended_model = "施耐德 RXM 24V DC"
        result.warnings.append("电流较大，建议选用接触器")
    
    return result


@dataclass
class FatigueResult:
    """疲劳强度校核结果"""
    stress_amplitude: float = 0.0       # 应力幅 MPa
    mean_stress: float = 0.0             # 平均应力 MPa
    fatigue_limit: float = 0.0          # 疲劳极限 MPa
    safety_factor: float = 0.0
    pass_fatigue: bool = False
    warnings: List[str] = field(default_factory=list)


def fatigue_check(
    max_stress: float,
    min_stress: float,
    material: str = "45钢",
) -> FatigueResult:
    """
    疲劳强度校核 (简化)
    
    Args:
        max_stress: 最大应力 MPa
        min_stress: 最小应力 MPa
        material: 材料
    
    Returns:
        FatigueResult
    """
    result = FatigueResult()
    
    # 疲劳极限
    fatigue_limits = {
        "45钢": 250,
        "40Cr": 350,
        "65Mn": 400,
    }
    result.fatigue_limit = fatigue_limits.get(material, 250)
    
    # 应力幅和平均应力
    result.stress_amplitude = (max_stress - min_stress) / 2
    result.mean_stress = (max_stress + min_stress) / 2
    
    # 安全系数 (简化古德曼公式)
    # n = σ_-1 / (σ_a + σ_m * σ_-1 / σ_b)
    # σ_b 取抗拉强度
    tensile_strength = {
        "45钢": 600,
        "40Cr": 980,
        "65Mn": 1000,
    }.get(material, 600)
    
    equivalent_stress = result.stress_amplitude + result.mean_stress * result.fatigue_limit / tensile_strength
    
    if equivalent_stress > 0:
        result.safety_factor = result.fatigue_limit / equivalent_stress
    
    # 校核 (安全系数 ≥ 1.5)
    result.pass_fatigue = result.safety_factor >= 1.5
    
    if not result.pass_fatigue:
        result.warnings.append(
            f"疲劳安全系数 {result.safety_factor:.2f} < 1.5，可能发生疲劳破坏"
        )
    
    return result
