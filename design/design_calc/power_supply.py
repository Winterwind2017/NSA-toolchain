"""
开关电源选型计算

24V/48V 工业开关电源选型计算。
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PowerSupplyResult:
    """开关电源选型结果"""
    total_current_a: float = 0.0        # 总电流 A
    total_power_w: float = 0.0          # 总功率 W
    recommended_power_w: float = 0.0   # 推荐功率 W
    recommended_model: str = ""         # 推荐型号
    input_voltage: float = 220.0        # 输入电压 V
    output_voltage: float = 24.0        # 输出电压 V
    efficiency: float = 0.85            # 效率
    warnings: List[str] = field(default_factory=list)


def power_supply_selection(
    devices: Dict[str, float],
    output_voltage: float = 24.0,
    spare_ratio: float = 0.3,
) -> PowerSupplyResult:
    """
    开关电源选型计算
    
    Args:
        devices: 设备字典 {"传感器": 0.1, "电磁阀": 0.5, ...} (单位: A)
        output_voltage: 输出电压 V
        spare_ratio: 备用功率比例
    
    Returns:
        PowerSupplyResult
    """
    result = PowerSupplyResult()
    result.output_voltage = output_voltage
    
    # 总电流
    total_current = sum(devices.values())
    result.total_current_a = total_current
    
    # 总功率
    result.total_power_w = total_current * output_voltage
    
    # 加备用功率
    required_power = result.total_power_w * (1 + spare_ratio)
    result.recommended_power_w = required_power
    
    # 标准电源功率
    standard_powers = [50, 100, 150, 200, 350, 500, 750, 1000]
    
    for power in standard_powers:
        if power >= required_power:
            result.recommended_power_w = power
            break
    else:
        result.recommended_power_w = 1000
        result.warnings.append("功率较大，建议多路电源")
    
    # 推荐型号
    result.recommended_model = f"明纬 NES-{int(result.recommended_power_w)}-24"
    
    return result


@dataclass
class SensorResult:
    """传感器选型结果"""
    sensor_type: str = ""               # 传感器类型
    detection_distance_mm: float = 0.0  # 检测距离 mm
    output_type: str = "NPN"            # 输出类型
    recommended_model: str = ""         # 推荐型号
    warnings: List[str] = field(default_factory=list)


def sensor_selection(
    target_material: str,
    detection_distance_mm: float,
    output_type: str = "NPN",
) -> SensorResult:
    """
    传感器选型计算
    
    Args:
        target_material: 检测物体材料
        detection_distance_mm: 检测距离 mm
        output_type: 输出类型 (NPN/PNP)
    
    Returns:
        SensorResult
    """
    result = SensorResult()
    result.detection_distance_mm = detection_distance_mm
    result.output_type = output_type
    
    # 选择传感器类型
    if target_material in ["金属", "钢", "铁", "铝", "铜"]:
        # 金属用接近开关
        result.sensor_type = "电感式接近开关"
        
        if detection_distance_mm <= 2:
            result.recommended_model = "欧姆龙 E2E-X2E1"
        elif detection_distance_mm <= 5:
            result.recommended_model = "欧姆龙 E2E-X5E1"
        elif detection_distance_mm <= 10:
            result.recommended_model = "欧姆龙 E2E-X10E1"
        else:
            result.recommended_model = "欧姆龙 E2E-X18E1"
            result.warnings.append("检测距离较远，建议选用光电传感器")
    
    elif target_material in ["透明", "玻璃", "塑料"]:
        # 透明物体用光纤传感器
        result.sensor_type = "光纤传感器"
        result.recommended_model = "欧姆龙 E3X-NA11"
    
    else:
        # 其他用光电传感器
        result.sensor_type = "漫反射光电开关"
        
        if detection_distance_mm <= 100:
            result.recommended_model = "欧姆龙 E3Z-D61"
        elif detection_distance_mm <= 500:
            result.recommended_model = "欧姆龙 E3Z-D62"
        else:
            result.recommended_model = "欧姆龙 E3Z-D82"
    
    return result


@dataclass
class GripperResult:
    """夹爪选型结果"""
    gripper_type: str = ""              # 夹爪类型
    grip_force_n: float = 0.0           # 夹持力 N
    jaw_stroke_mm: float = 0.0          # 行程 mm
    recommended_model: str = ""         # 推荐型号
    warnings: List[str] = field(default_factory=list)


def gripper_selection(
    payload_kg: float,
    object_size_mm: float = 50.0,
    gripper_type: str = "parallel",
) -> GripperResult:
    """
    夹爪选型计算
    
    Args:
        payload_kg: 夹持重量 kg
        object_size_mm: 物体尺寸 mm
        gripper_type: 夹爪类型 (parallel/angular/three_finger)
    
    Returns:
        GripperResult
    """
    result = GripperResult()
    
    g = 9.81
    
    # 所需夹持力 (安全系数 2)
    required_force = payload_kg * g * 2
    result.grip_force_n = required_force
    
    # 行程
    result.jaw_stroke_mm = object_size_mm
    
    # 类型
    type_names = {
        "parallel": "平行夹爪",
        "angular": "角度夹爪",
        "three_finger": "三爪夹爪",
    }
    result.gripper_type = type_names.get(gripper_type, "平行夹爪")
    
    # 推荐型号
    if required_force < 10:
        result.recommended_model = "SMC MHZ2-6D"
    elif required_force < 30:
        result.recommended_model = "SMC MHZ2-16D"
    elif required_force < 80:
        result.recommended_model = "SMC MHZ2-25D"
    elif required_force < 150:
        result.recommended_model = "SMC MHZ2-32D"
    else:
        result.recommended_model = "SMC MHZ2-40D"
        result.warnings.append("夹持力较大，建议选用电动夹爪")
    
    return result
