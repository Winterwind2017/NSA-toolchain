"""
气动回路与元件选型辅助计算

种类推荐、气源处理、耗气、阀、真空。
公式来源: SMC/亚德客选型手册、气动设计经验、BV13t896UEWL P9 大纲
"""

import math


def recommend_actuator(
    motion: str = "linear",
    stroke_mm: float = 50.0,
    force_n: float = 100.0,
    lateral_load: bool = False,
    space_limited: bool = False,
    vertical: bool = False,
    high_force: bool = False,
    clean: bool = False,
    grip_open_deg: float = 0.0,
    workpiece: str = "rigid",
) -> dict:
    """
    先定气动执行器种类，再交给 cylinder / vacuum_cup_check / valve_select。

    Args:
        motion: 'linear' / 'rotary' / 'grip' / 'vacuum' / 'clamp'
        stroke_mm: 直线行程 mm
        force_n: 预估负载力 N
        lateral_load: 有明显横向力或抗扭需求
        space_limited: 轴向空间紧
        vertical: 垂直轴
        high_force: 压装/冲裁，气源仍约 0.5 MPa 但要很大出力
        clean: 要隔离、少泄漏
        grip_open_deg: 手指需要的开闭角，≥150 用 180° 型
        workpiece: 'rigid' / 'fragile' / 'porous' / 'bag'
    """
    notes: list = []
    if vertical:
        notes.append("垂直轴失电必须回安全位或加机械锁，阀用失电回位或保压")

    if motion == "vacuum" or workpiece in ("bag", "porous"):
        if workpiece == "bag":
            cup = "波纹/海绵吸盘"
            reason = "薄膜或袋装，平面吸盘贴不严"
        elif workpiece == "porous":
            cup = "大直径吸盘或多只 + 真空泵"
            reason = "漏气件发生器往往吸不住"
            notes.append("水平安全系数≥4，垂直≥8，用 vacuum_cup_check")
        elif workpiece == "fragile":
            cup = "硅橡胶吸盘"
            reason = "易留痕或食品接触"
        else:
            cup = "丁腈扁平吸盘 + 真空发生器"
            reason = "刚性件间断吸取"
        notes.append("真空回路单独减压，不要和夹紧缸共一路")
        return {"actuator": cup, "reason": reason, "notes": notes, "next": "vacuum_cup_check"}

    if motion == "grip":
        actuator = "气动手指 180°开闭" if grip_open_deg >= 150 else "气动手指 平行开闭"
        reason = "刚性件夹持、开闭角明确"
        notes.append("夹持力按摩擦和姿态取安全系数；力矩交给导杆或模组")
        return {"actuator": actuator, "reason": reason, "notes": notes, "next": "厂家手指力矩表"}

    if motion == "clamp":
        return {
            "actuator": "夹紧气缸（杠杆/肘节）",
            "reason": "行程短、夹紧力大",
            "notes": notes,
            "next": "cylinder.select_bore",
        }

    if motion == "rotary":
        notes.append("只适合有限转角；要连续旋转改电机")
        return {
            "actuator": "旋转气缸",
            "reason": "90°/180°/270° 两点或有限位转角",
            "notes": notes,
            "next": "厂家转角/力矩表",
        }

    # linear
    if high_force or force_n >= 5000:
        notes.append("气液增压是两点压装，要力曲线或位置伺服则改伺服压机")
        return {
            "actuator": "气液增压缸",
            "reason": "气源仍约 0.5 MPa 但出力要到吨级",
            "notes": notes,
            "next": "厂家增压比样本",
        }

    if stroke_mm >= 400:
        if clean and not lateral_load and force_n < 400:
            actuator = "无杆气缸（磁耦合）"
            reason = "长行程且要隔离、负载不大"
            notes.append("过载会滑脱，当开环丢步处理")
        else:
            actuator = "无杆气缸（机械接合）"
            reason = "长行程，活塞杆伸出机架不划算"
            if lateral_load:
                notes.append("无杆必须带导轨滑块或外加导轨")
        notes.append("调速用排气节流；阀到缸管长 <1 m")
        return {"actuator": actuator, "reason": reason, "notes": notes, "next": "cylinder.select_bore"}

    if lateral_load:
        actuator = "带导杆气缸" if not space_limited else "三轴/薄型导杆气缸"
        reason = "横向力超过普通活塞杆允许值（约推力 1/20）"
        return {"actuator": actuator, "reason": reason, "notes": notes, "next": "cylinder.check_lateral_load"}

    if space_limited and stroke_mm <= 80:
        return {
            "actuator": "薄型/紧凑气缸",
            "reason": "短行程、轴向空间紧",
            "notes": notes + ["偏载仍要外导轨，不要用薄型硬扛力矩"],
            "next": "cylinder.select_bore",
        }

    notes.append("速度默认两侧排气节流；完成信号用磁性开关")
    return {
        "actuator": "标准双作用气缸",
        "reason": "两点到位的默认直线执行器",
        "notes": notes,
        "next": "cylinder.select_bore",
    }


def recommend_frl(
    precision_valve: bool = False,
    vacuum_or_sensor: bool = True,
    old_need_oil: bool = False,
) -> dict:
    """气源处理：过滤精度、是否上油雾器。"""
    filt = "5 μm" if precision_valve else "40 μm"
    notes = ["工作压力 0.4~0.6 MPa，真空发生器单独减压"]
    if old_need_oil and not vacuum_or_sensor:
        lube = "加油雾器"
    else:
        lube = "不加油雾器"
        notes.append("无油缸、真空、阀岛禁止油雾")
        if old_need_oil:
            notes.append("回路里有真空或阀岛时不要为老式缸加全线油雾，应隔离供油")
    return {
        "filter": filt,
        "regulator_mpa": "0.4~0.6",
        "lubricator": lube,
        "notes": notes,
    }


def air_consumption(
    bore_mm: float,
    stroke_mm: float,
    pressure_mpa: float,
    cycles_per_min: float,
    action: str = "double",
) -> dict:
    """
    气缸耗气量计算

    Args:
        bore_mm: 缸径 mm
        stroke_mm: 行程 mm
        pressure_mpa: 工作压力 MPa
        cycles_per_min: 每分钟往复次数
        action: 'double' 双作用 / 'single' 单作用

    Returns:
        dict 耗气量 (L/min ANR)
    """
    # 气缸容积 (L)
    area_cm2 = math.pi / 4 * (bore_mm / 10) ** 2  # cm²
    stroke_cm = stroke_mm / 10
    vol_push = area_cm2 * stroke_cm / 1000  # L

    if action == "double":
        rod_d = 0.3 * bore_mm
        rod_area = math.pi / 4 * (rod_d / 10) ** 2
        vol_pull = (area_cm2 - rod_area) * stroke_cm / 1000
        vol_per_cycle = vol_push + vol_pull
    else:
        vol_per_cycle = vol_push

    # 压缩比
    compression_ratio = (pressure_mpa * 10 + 1.013) / 1.013  # 绝对压力/大气压

    # 耗气量 L/min (ANR = 标准状态)
    q = vol_per_cycle * cycles_per_min * compression_ratio

    return {
        "volume_per_cycle_L": round(vol_per_cycle, 4),
        "compression_ratio": round(compression_ratio, 2),
        "consumption_L_min_ANR": round(q, 2),
    }


def pipe_size(bore_mm: float) -> str:
    """根据缸径推荐气管规格"""
    if bore_mm <= 16:
        return "Φ4"
    elif bore_mm <= 32:
        return "Φ6"
    elif bore_mm <= 63:
        return "Φ8"
    elif bore_mm <= 100:
        return "Φ10"
    else:
        return "Φ12"


def valve_type(action: str, need_mid_stop: bool = False) -> str:
    """推荐电磁阀类型（兼容旧接口）"""
    return valve_select(action=action, need_mid_stop=need_mid_stop)["valve"]


def valve_select(
    action: str = "double",
    need_mid_stop: bool = False,
    mid_stop_mode: str = "closed",
    hold_on_power_loss: bool = False,
    allow_manual_move: bool = False,
    vertical_load: bool = False,
    valve_count: int = 1,
) -> dict:
    """
    电磁阀选型。

    Args:
        action: 'single' 单作用 / 'double' 双作用 / 'blow' 吹气通断 / 'vacuum' 真空
        need_mid_stop: 是否要中途停止
        mid_stop_mode: 'closed' 中封 / 'exhaust' 中泄 / 'pressure' 中压
        hold_on_power_loss: 失电保持当前位置
        allow_manual_move: 中停时还要能手推对位
        vertical_load: 垂直负载（中封不够，需保压或机械锁）
        valve_count: 本机电磁阀数量，>=4 建议阀岛
    """
    notes = []
    if action in ("blow", "vacuum"):
        valve = "2/2通常闭" if action == "blow" else "真空阀或3/2通（发生器）+ 2/2破坏阀"
        solenoid = "单电控"
    elif action == "single":
        valve = "3/2通"
        solenoid = "单电控（弹簧复位）"
    elif need_mid_stop:
        if allow_manual_move:
            mid_stop_mode = "exhaust"
        mode_cn = {"closed": "中封", "exhaust": "中泄", "pressure": "中压"}[mid_stop_mode]
        valve = f"5/3通{mode_cn}"
        solenoid = "双电控"
        if mid_stop_mode == "closed" and vertical_load:
            notes.append("中封不能当刹车，垂直负载加气动保压阀或机械锁")
        if allow_manual_move and mid_stop_mode != "exhaust":
            notes.append("要手推对位应改中泄")
    else:
        valve = "5/2通"
        solenoid = "双电控（失电保持）" if hold_on_power_loss else "单电控（弹簧复位，默认失电回位）"

    notes.append("线圈 DC24V，PLC 输出加续流")
    notes.append("双电控两线圈必须互锁")
    if valve_count >= 4:
        notes.append("阀数>=4，优先阀岛，工位号与 I/O 同名")

    return {
        "valve": f"{valve} ({solenoid})",
        "function": valve,
        "solenoid": solenoid,
        "voltage": "DC24V",
        "manifold": valve_count >= 4,
        "notes": notes,
    }


def response_time_check(
    tube_length_m: float,
    tube_id_mm: float,
    cylinder_volume_L: float,
) -> dict:
    """
    气管响应时间估算

    经验公式: 管长 > 1m 时响应明显滞后

    Args:
        tube_length_m: 阀到缸的管长 m
        tube_id_mm: 气管内径 mm
        cylinder_volume_L: 气缸单侧容积 L

    Returns:
        dict 响应评估
    """
    tube_volume = math.pi / 4 * (tube_id_mm / 1000) ** 2 * tube_length_m * 1000  # L
    total_volume = tube_volume + cylinder_volume

    # 经验: 充排气时间 ≈ 总容积 / 阀流量
    # 简化评估
    if tube_length_m < 0.5:
        level = "优 (阀紧邻缸)"
    elif tube_length_m < 1.0:
        level = "良"
    elif tube_length_m < 2.0:
        level = "中 (建议放大管径)"
    else:
        level = "差 (必须放大管径或阀装缸旁)"

    return {
        "tube_volume_L": round(tube_volume, 4),
        "total_volume_L": round(total_volume, 4),
        "tube_length_m": tube_length_m,
        "response_level": level,
    }


def vacuum_cup_check(
    cup_diameter_mm: float,
    vacuum_kpa: float,
    load_kg: float,
    safety_factor: float = 4.0,
    cups: int = 1,
) -> dict:
    """
    真空吸盘吸力校核

    Args:
        cup_diameter_mm: 吸盘直径 mm
        vacuum_kpa: 真空度 kPa (负值取绝对值)
        load_kg: 负载质量 kg
        safety_factor: 安全系数 (水平≥4, 垂直≥8)
        cups: 吸盘数量

    Returns:
        dict 校核结果
    """
    area_m2 = math.pi / 4 * (cup_diameter_mm / 1000) ** 2
    force_per_cup = vacuum_kpa * 1000 * area_m2  # N (kPa→Pa)
    total_force = force_per_cup * cups
    required = load_kg * 9.81 * safety_factor

    return {
        "force_per_cup_N": round(force_per_cup, 2),
        "total_force_N": round(total_force, 2),
        "required_N": round(required, 2),
        "actual_safety_factor": round(total_force / (load_kg * 9.81), 1),
        "pass": total_force >= required,
    }
