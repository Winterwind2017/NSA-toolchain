"""
密封件/安全/布局计算

密封件选型、安全回路设计、设备布局计算。
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SealResult:
    """密封件选型结果"""
    seal_type: str = ""                  # 密封类型
    groove_size: str = ""                # 沟槽尺寸
    material: str = ""                   # 材料
    recommended_model: str = ""         # 推荐型号
    warnings: List[str] = field(default_factory=list)


def seal_selection(
    shaft_dia_mm: float,
    pressure_mpa: float = 0.5,
    temperature_c: float = 80.0,
    medium: str = "air",
) -> SealResult:
    """
    密封件选型计算
    
    Args:
        shaft_dia_mm: 轴径 mm
        pressure_mpa: 工作压力 MPa
        temperature_c: 工作温度 ℃
        medium: 介质 (air/oil/water)
    
    Returns:
        SealResult
    """
    result = SealResult()
    
    # 密封类型
    if pressure_mpa < 1:
        result.seal_type = "O型圈"
    elif pressure_mpa < 10:
        result.seal_type = "Y型圈"
    else:
        result.seal_type = "格莱圈"
        result.warnings.append("压力较高，建议选用格莱圈")
    
    # 材料选择
    if medium == "air" and temperature_c <= 80:
        result.material = "NBR (丁腈橡胶)"
    elif temperature_c <= 120:
        result.material = "NBR (丁腈橡胶)"
    elif temperature_c <= 200:
        result.material = "FKM (氟橡胶)"
    else:
        result.material = "FFKM (全氟醚橡胶)"
        result.warnings.append("温度较高，建议选用全氟醚橡胶")
    
    # 推荐型号
    result.recommended_model = f"O-Ring {int(shaft_dia_mm)} × 2.5"
    
    return result


@dataclass
class SafetyCircuitResult:
    """安全回路设计结果"""
    safety_category: str = ""            # 安全等级
    emergency_stop: bool = True          # 急停按钮
    safety_gate: bool = False            # 安全门开关
    light_curtain: bool = False          # 安全光幕
    warnings: List[str] = field(default_factory=list)


def safety_circuit_design(
    risk_level: str = "medium",
    has_moving_parts: bool = True,
    operator_access: bool = True,
) -> SafetyCircuitResult:
    """
    安全回路设计
    
    Args:
        risk_level: 风险等级 (low/medium/high)
        has_moving_parts: 是否有运动部件
        operator_access: 操作人员是否可接触
    
    Returns:
        SafetyCircuitResult
    """
    result = SafetyCircuitResult()
    
    # 安全等级
    if risk_level == "low":
        result.safety_category = "B级 (CAT.B)"
    elif risk_level == "medium":
        result.safety_category = "1级 (CAT.1)"
    else:
        result.safety_category = "3级 (CAT.3)"
    
    # 安全元件
    result.emergency_stop = True  # 所有设备都需要急停
    
    if has_moving_parts and operator_access:
        result.safety_gate = True
        result.warnings.append("建议加装安全门开关")
    
    if risk_level == "high" and operator_access:
        result.light_curtain = True
        result.warnings.append("建议加装安全光幕")
    
    return result


@dataclass
class LayoutResult:
    """设备布局计算结果"""
    machine_length_mm: float = 0.0       # 设备长度 mm
    machine_width_mm: float = 0.0        # 设备宽度 mm
    access_space_mm: float = 800.0      # 维护空间 mm
    total_length_mm: float = 0.0        # 总长度 mm
    total_width_mm: float = 0.0         # 总宽度 mm
    warnings: List[str] = field(default_factory=list)


def equipment_layout(
    machine_length_mm: float,
    machine_width_mm: float,
    has_input_conveyor: bool = True,
    has_output_conveyor: bool = True,
) -> LayoutResult:
    """
    设备布局计算 (含上下料空间)
    
    Args:
        machine_length_mm: 设备本体长度 mm
        machine_width_mm: 设备本体宽度 mm
        has_input_conveyor: 是否有进料线
        has_output_conveyor: 是否有出料线
    
    Returns:
        LayoutResult
    """
    result = LayoutResult()
    result.machine_length_mm = machine_length_mm
    result.machine_width_mm = machine_width_mm
    
    # 总长度 (含进出料)
    total_length = machine_length_mm
    if has_input_conveyor:
        total_length += 500  # 进料段 500mm
    if has_output_conveyor:
        total_length += 500  # 出料段 500mm
    
    # 加维护空间
    total_length += 2 * result.access_space_mm
    total_width = machine_width_mm + 2 * result.access_space_mm
    
    result.total_length_mm = total_length
    result.total_width_mm = total_width
    
    return result
