"""
电气选型计算

电缆选型、断路器选型、PLC IO 点数计算。
公式来源: 电气设计手册、国标 GB
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class CableResult:
    """电缆选型结果"""
    rated_current_a: float = 0.0       # 额定电流 A
    voltage_drop_v: float = 0.0         # 电压降 V
    recommended_size_mm2: float = 0.0  # 推荐截面积 mm²
    cable_type: str = ""                # 电缆类型
    warnings: List[str] = field(default_factory=list)


def cable_selection(
    power_kw: float,
    voltage_v: float = 220.0,
    length_m: float = 10.0,
    power_factor: float = 0.85,
    three_phase: bool = True,
) -> CableResult:
    """
    电缆选型计算
    
    Args:
        power_kw: 功率 kW
        voltage_v: 电压 V
        length_m: 电缆长度 m
        power_factor: 功率因数
        three_phase: 是否三相
    
    Returns:
        CableResult
    """
    result = CableResult()
    
    # 计算电流
    if three_phase:
        # P = √3 * U * I * cosφ
        current = power_kw * 1000 / (math.sqrt(3) * voltage_v * power_factor)
    else:
        # P = U * I * cosφ
        current = power_kw * 1000 / (voltage_v * power_factor)
    
    result.rated_current_a = current
    
    # 电缆截面积选择 (根据电流)
    # 铜芯电缆载流量参考
    cable_sizes = [
        (0.75, 10),
        (1.0, 14),
        (1.5, 18),
        (2.5, 26),
        (4.0, 35),
        (6.0, 48),
        (10.0, 65),
        (16.0, 90),
        (25.0, 120),
    ]
    
    for size, ampacity in cable_sizes:
        if current <= ampacity * 0.8:  # 80% 余量
            result.recommended_size_mm2 = size
            break
    else:
        result.recommended_size_mm2 = 25.0
        result.warnings.append("功率较大，建议更大电缆")
    
    # 电压降计算
    # ΔU = I * L * ρ / S
    rho = 0.0175  # 铜电阻率 Ω·mm²/m
    voltage_drop = current * length_m * rho / result.recommended_size_mm2
    result.voltage_drop_v = voltage_drop
    
    # 电压降校核 (<5%)
    if voltage_drop > voltage_v * 0.05:
        result.warnings.append(
            f"电压降 {voltage_drop:.1f} V 超过 5%，建议增大电缆截面积"
        )
    
    # 电缆类型
    if three_phase:
        result.cable_type = f"RVV {result.recommended_size_mm2:.1f}×3+1"
    else:
        result.cable_type = f"RVV {result.recommended_size_mm2:.1f}×2"
    
    return result


@dataclass
class CircuitBreakerResult:
    """断路器选型结果"""
    rated_current_a: float = 0.0
    recommended_amp_a: float = 0.0
    breaker_type: str = ""
    poles: int = 2
    warnings: List[str] = field(default_factory=list)


def circuit_breaker_selection(
    load_current_a: float,
    starting_current_multiplier: float = 3.0,
    voltage_v: float = 220.0,
) -> CircuitBreakerResult:
    """
    断路器选型计算
    
    Args:
        load_current_a: 负载额定电流 A
        starting_current_multiplier: 启动电流倍数
        voltage_v: 电压 V
    
    Returns:
        CircuitBreakerResult
    """
    result = CircuitBreakerResult()
    result.rated_current_a = load_current_a
    
    # 考虑启动电流
    required_current = load_current_a * 1.5  # 1.5倍余量
    
    # 标准断路器额定电流
    standard_amps = [6, 10, 16, 20, 25, 32, 40, 63, 100]
    
    for amp in standard_amps:
        if amp >= required_current:
            result.recommended_amp_a = amp
            break
    else:
        result.recommended_amp_a = 100
        result.warnings.append("电流较大，建议更大断路器")
    
    # 断路器类型
    if starting_current_multiplier <= 3:
        result.breaker_type = "C型"
    else:
        result.breaker_type = "D型"
    
    # 极数
    result.poles = 2 if voltage_v <= 220 else 3
    
    return result


@dataclass
class PLCIOResult:
    """PLC IO 点数统计结果"""
    digital_inputs: int = 0
    digital_outputs: int = 0
    analog_inputs: int = 0
    analog_outputs: int = 0
    total_io: int = 0
    recommended_plc: str = ""
    warnings: List[str] = field(default_factory=list)


def plc_io_calculation(
    sensors: Dict[str, int] = None,
    actuators: Dict[str, int] = None,
    analog_devices: int = 0,
    spare_ratio: float = 0.2,
) -> PLCIOResult:
    """
    PLC IO 点数计算
    
    Args:
        sensors: 传感器字典 {"光电开关": 5, "接近开关": 3, ...}
        actuators: 执行器字典 {"电磁阀": 4, "指示灯": 6, ...}
        analog_devices: 模拟量设备数量
        spare_ratio: 备用点比例
    
    Returns:
        PLCIOResult
    """
    result = PLCIOResult()
    
    # 默认值
    if sensors is None:
        sensors = {}
    if actuators is None:
        actuators = {}
    
    # 数字量输入 (传感器)
    result.digital_inputs = sum(sensors.values())
    
    # 数字量输出 (执行器)
    result.digital_outputs = sum(actuators.values())
    
    # 模拟量
    result.analog_inputs = analog_devices
    result.analog_outputs = analog_devices // 2
    
    # 加备用点
    spare_di = int(result.digital_inputs * spare_ratio)
    spare_do = int(result.digital_outputs * spare_ratio)
    result.digital_inputs += spare_di
    result.digital_outputs += spare_do
    
    # 总点数
    result.total_io = (
        result.digital_inputs +
        result.digital_outputs +
        result.analog_inputs +
        result.analog_outputs
    )
    
    # 推荐 PLC
    total_dio = result.digital_inputs + result.digital_outputs
    
    if total_dio <= 30:
        result.recommended_plc = "西门子 S7-200 SMART"
    elif total_dio <= 60:
        result.recommended_plc = "西门子 S7-1200"
    elif total_dio <= 128:
        result.recommended_plc = "西门子 S7-1500"
    else:
        result.recommended_plc = "西门子 S7-1500 (扩展模块)"
        result.warnings.append("IO 点数较多，建议采用分布式 IO")
    
    return result
