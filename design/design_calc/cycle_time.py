"""
设备节拍 / 时序计算

串联相加，并联取最长，不要把所有动作时间直接求和。
"""

from __future__ import annotations

from typing import Iterable, Sequence


def series(times: Iterable[float]) -> float:
    """串联：关键路径上的时间相加。"""
    return float(sum(times))


def parallel(times: Iterable[float]) -> float:
    """并联：同时进行，取最长。"""
    values = list(times)
    if not values:
        raise ValueError("parallel() 需要至少一段动作时间")
    return float(max(values))


def overlap(t1: float, t2: float, shared: float) -> float:
    """两段部分重叠。shared 不能大于较短的那段。"""
    if shared < 0:
        raise ValueError("重叠时间不能为负")
    if shared > min(t1, t2):
        raise ValueError("重叠时间不能超过较短动作")
    return t1 + t2 - shared


def cylinder_stroke_time(
    stroke_mm: float,
    avg_speed_mm_s: float = 250.0,
    valve_delay_s: float = 0.025,
    cushion_s: float = 0.04,
) -> float:
    """气缸单向时间：行程/平均速度 + 阀响应 + 末端缓冲。"""
    if avg_speed_mm_s <= 0:
        raise ValueError("平均速度必须大于 0")
    return stroke_mm / avg_speed_mm_s + valve_delay_s + cushion_s


def servo_move_time(
    distance_mm: float,
    vmax_mm_s: float,
    accel_mm_s2: float,
    settle_s: float = 0.05,
) -> float:
    """
    伺服点到点时间（加减速对称三角/梯形）。
    短行程到不了 vmax 时按三角曲线。
    """
    if vmax_mm_s <= 0 or accel_mm_s2 <= 0:
        raise ValueError("速度和加速度必须大于 0")
    d_accel = vmax_mm_s**2 / accel_mm_s2
    if distance_mm <= d_accel:
        return 2.0 * (distance_mm / accel_mm_s2) ** 0.5 + settle_s
    t_acc = vmax_mm_s / accel_mm_s2
    t_cruise = (distance_mm - d_accel) / vmax_mm_s
    return 2.0 * t_acc + t_cruise + settle_s


def cycle_time(
    critical_path_s: float,
    reset_s: float = 0.0,
    margin: float = 1.2,
) -> dict:
    """
    单站节拍。

    Args:
        critical_path_s: 进料到出料的关键路径（已处理串并联）
        reset_s: 必须串在窗口内的复位/让路
        margin: 方案余量，默认 1.2
    """
    if critical_path_s < 0 or reset_s < 0:
        raise ValueError("时间不能为负")
    if margin < 1.0:
        raise ValueError("余量应 >= 1.0")
    raw = critical_path_s + reset_s
    ct = raw * margin
    return {
        "critical_path_s": round(critical_path_s, 4),
        "reset_s": round(reset_s, 4),
        "raw_s": round(raw, 4),
        "margin": margin,
        "cycle_time_s": round(ct, 4),
        "uph_single": round(3600.0 / ct, 1) if ct else 0.0,
    }


def uph(cycle_time_s: float, stations: int = 1, yield_rate: float = 1.0) -> float:
    """小时产量。多工位并行时 stations>1。"""
    if cycle_time_s <= 0:
        raise ValueError("节拍必须大于 0")
    if not 0 < yield_rate <= 1:
        raise ValueError("良率应在 (0, 1]")
    return round(3600.0 / cycle_time_s * stations * yield_rate, 1)


def meets_target(cycle_time_s: float, target_s: float) -> dict:
    """是否满足客户节拍。"""
    ok = cycle_time_s <= target_s
    return {
        "ok": ok,
        "cycle_time_s": cycle_time_s,
        "target_s": target_s,
        "slack_s": round(target_s - cycle_time_s, 4),
        "advice": "满足" if ok else "超节拍：先并联，再压缩工艺时间，最后换更快的执行器",
    }


def from_steps(steps: Sequence[dict]) -> dict:
    """
    由动作表估算关键路径。

    每个 step: {"name", "time", "group"}
    同一 group 内并联（取 max），不同 group 按列表顺序串联。
    group 为空则视为独立串联步。
    """
    groups: list[tuple[str, list[float], list[str]]] = []
    index: dict[str, int] = {}
    for step in steps:
        name = step["name"]
        t = float(step["time"])
        group = step.get("group") or f"__solo_{name}_{len(groups)}"
        if group in index:
            groups[index[group]][1].append(t)
            groups[index[group]][2].append(name)
        else:
            index[group] = len(groups)
            groups.append((group, [t], [name]))

    path = 0.0
    breakdown = []
    for group, times, names in groups:
        dt = parallel(times) if len(times) > 1 else times[0]
        path += dt
        breakdown.append(
            {
                "group": group,
                "actions": names,
                "mode": "parallel" if len(times) > 1 else "series",
                "time_s": round(dt, 4),
            }
        )
    return {
        "critical_path_s": round(path, 4),
        "steps": breakdown,
    }
