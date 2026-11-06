"""齿轮**检验尺寸**：公法线长度、跨棒距、分度圆齿厚。

出图时检验员要的不是"渐开线轮廓"，而是几个能拿卡尺/公法线千分尺量的数——
这里按 ISO/GB 的经典公式算，并显式区分外齿与内齿（符号相反，最容易写错）。

公法线长度（跨 k 齿）::

    k  = round(z·α/180° + 0.5)                 α 用度
    W_k = m·cosα·[π(k − 0.5) + z·invα] + 2·x·m·sinα

跨棒距（量柱/量球）::

    inv α_M = inv α + d_p/d_b − π/(2z) + 2·x·tanα/z        （外齿）
    inv α_M = inv α − d_p/d_b + π/(2z) − 2·x·tanα/z        （内齿）
    M = d_b/cos α_M + d_p        （外齿，偶数齿）
    M = d_b·cos(π/2z)/cos α_M + d_p   （外齿，奇数齿）
    M = d_b/cos α_M − d_p        （内齿，偶数齿）
    M = d_b·cos(π/2z)/cos α_M − d_p   （内齿，奇数齿）

量柱直径默认取 ``1.68·m``（α=20° 的经验值），也可以用标准量棒系列里的实际值。
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import ContractError, require_positive
from .internal_gear import InternalGearSpec
from .involute_gear import InvoluteGearSpec, involute_angle

#: 量柱直径相对模数的经验系数（α=20°）
PIN_DIAMETER_FACTOR = 1.68


def _solve_involute(target: float) -> float:
    """解 inv(θ) = target，返回 θ（弧度）。"""
    if target <= 0.0:
        return 0.0
    theta = 1.0
    for _ in range(60):
        inv = math.tan(theta) - theta
        derivative = math.tan(theta) ** 2
        if derivative < 1e-12:
            break
        step = (inv - target) / derivative
        theta -= step
        if abs(step) < 1e-14:
            break
    return theta


def span_normal_step(module_mm: float, pressure_angle_deg: float) -> float:
    """法向基节 π·m·cosα：跨 k+1 齿比跨 k 齿正好长这么多。"""
    return math.pi * module_mm * math.cos(math.radians(pressure_angle_deg))


def tooth_thickness_at_pitch(spec: InvoluteGearSpec) -> float:
    """分度圆齿厚 s = m(π/2 + 2x·tanα)。"""
    shift = getattr(spec, "profile_shift_x", 0.0)
    return spec.module_mm * (math.pi / 2.0
                             + 2.0 * shift * math.tan(math.radians(spec.pressure_angle_deg)))


def span_measurement(spec: InvoluteGearSpec, k: int | None = None) -> dict[str, Any]:
    """公法线长度（跨 k 齿）。``k`` 不给时按标准规则取。"""
    alpha = math.radians(spec.pressure_angle_deg)
    shift = getattr(spec, "profile_shift_x", 0.0)
    if k is None:
        k = int(round(spec.tooth_count * spec.pressure_angle_deg / 180.0 + 0.5))
    if not isinstance(k, int) or k < 2:
        raise ContractError("k must be an integer >= 2")
    if k > spec.tooth_count - 1:
        raise ContractError("k too large for this tooth count")

    involute = involute_angle(spec.pitch_radius_mm, spec.base_radius_mm)
    length = (spec.module_mm * math.cos(alpha)
              * (math.pi * (k - 0.5) + spec.tooth_count * involute)
              + 2.0 * shift * spec.module_mm * math.sin(alpha))
    return {
        "k": k,
        "span_length_mm": round(length, 4),
        "span_rule": "k = round(z·α/180° + 0.5)",
        "pressure_angle_deg": spec.pressure_angle_deg,
    }


def span_over_pins(spec: InvoluteGearSpec, pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """外齿跨棒距 M（偶数齿 +d_p，奇数齿按 cos(π/2z) 修正）。"""
    alpha = math.radians(spec.pressure_angle_deg)
    shift = getattr(spec, "profile_shift_x", 0.0)
    pin = float(pin_diameter_mm) if pin_diameter_mm else \
        require_positive(PIN_DIAMETER_FACTOR * spec.module_mm, "pin_diameter_mm")
    if pin <= 0.0:
        raise ContractError("pin_diameter_mm must be positive")

    base = spec.base_radius_mm
    target = (involute_angle(spec.pitch_radius_mm, base) + pin / (2.0 * base)
              - math.pi / (2.0 * spec.tooth_count)
              + 2.0 * shift * math.tan(alpha) / spec.tooth_count)
    alpha_m = _solve_involute(target)
    cos_m = math.cos(alpha_m)
    if cos_m <= 1e-9:
        raise ContractError("量柱过大：α_M 接近 90°，跨棒距无解")
    if spec.tooth_count % 2 == 0:
        distance = 2.0 * base / cos_m + pin
    else:
        distance = 2.0 * base * math.cos(math.pi / (2.0 * spec.tooth_count)) / cos_m + pin
    return {
        "pin_diameter_mm": round(pin, 4),
        "alpha_M_deg": round(math.degrees(alpha_m), 4),
        "span_mm": round(distance, 4),
        "even_teeth": spec.tooth_count % 2 == 0,
    }


def span_over_pins_internal(spec: InternalGearSpec,
                            pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """内齿跨棒距：M = d_b/cos α_M − d_p（偶数齿）。"""
    alpha = math.radians(spec.pressure_angle_deg)
    shift = spec.profile_shift_x
    pin = float(pin_diameter_mm) if pin_diameter_mm else \
        require_positive(PIN_DIAMETER_FACTOR * spec.module_mm, "pin_diameter_mm")

    base = spec.base_radius_mm
    target = (involute_angle(spec.pitch_radius_mm, base) - pin / (2.0 * base)
              + math.pi / (2.0 * spec.tooth_count)
              - 2.0 * shift * math.tan(alpha) / spec.tooth_count)
    if target <= 0.0:
        raise ContractError("内齿跨棒距无解：量柱相对基圆太大")
    alpha_m = _solve_involute(target)
    cos_m = math.cos(alpha_m)
    if cos_m <= 1e-9:
        raise ContractError("量柱过大：α_M 接近 90°，跨棒距无解")
    if spec.tooth_count % 2 == 0:
        distance = 2.0 * base / cos_m - pin
    else:
        distance = 2.0 * base * math.cos(math.pi / (2.0 * spec.tooth_count)) / cos_m - pin
    if distance <= 0.0:
        raise ContractError("内齿跨棒距为负：量柱选得过大")
    return {
        "pin_diameter_mm": round(pin, 4),
        "alpha_M_deg": round(math.degrees(alpha_m), 4),
        "span_mm": round(distance, 4),
        "even_teeth": spec.tooth_count % 2 == 0,
    }



def helical_gear_inspection(spec: "HelicalGearSpec",
                            ball_diameter_mm: float | None = None) -> dict[str, Any]:
    """斜齿轮检验尺寸：法向公法线 + **量球**跨棒距。

    斜齿轮的齿是拧着的，所以：

    * 公法线只能在**法向**用专用量具量（沿法向跨 k 齿）；
    * 跨棒距必须用**量球**——量柱会顺着螺旋面滑走，量不住。

    工程上按**当量直齿轮**（virtual spur gear）算，这是手册通行做法：

        z_v = z / cos³β          m_n（法向模数）    α_n（法向压力角）

    ``z_v`` 不是整数没关系，公式本来就是连续的。
    """
    from .helical_gear import HelicalGearSpec          # 避免循环导入

    if not isinstance(spec, HelicalGearSpec):
        raise ContractError("helical_gear_inspection expects a HelicalGearSpec")

    beta = math.radians(spec.helix_angle_deg)
    alpha_n = math.radians(spec.pressure_angle_normal_deg)
    cos_beta = math.cos(beta)
    if cos_beta <= 1e-6:
        raise ContractError("螺旋角过大：cosβ 接近 0")

    virtual_teeth = spec.tooth_count / (cos_beta ** 3)
    module_n = spec.module_normal_mm
    pitch_v = module_n * virtual_teeth / 2.0
    base_v = pitch_v * math.cos(alpha_n)
    inv_alpha_n = math.tan(alpha_n) - alpha_n

    k = int(round(virtual_teeth * spec.pressure_angle_normal_deg / 180.0 + 0.5))
    if k < 2:
        raise ContractError("当量齿数太小，算不出公法线")
    span_length = (module_n * math.cos(alpha_n)
                   * (math.pi * (k - 0.5) + virtual_teeth * inv_alpha_n))

    ball = float(ball_diameter_mm) if ball_diameter_mm else \
        require_positive(PIN_DIAMETER_FACTOR * module_n, "ball_diameter_mm")
    target = inv_alpha_n + ball / (2.0 * base_v) - math.pi / (2.0 * virtual_teeth)
    if target <= 0.0:
        raise ContractError("量球相对当量基圆太大：跨棒距无解")
    alpha_m = _solve_involute(target)
    cos_m = math.cos(alpha_m)
    if cos_m <= 1e-9:
        raise ContractError("量球过大：α_M 接近 90°，跨棒距无解")
    if spec.tooth_count % 2 == 0:
        span = 2.0 * base_v / cos_m + ball
    else:
        span = 2.0 * base_v * math.cos(math.pi / (2.0 * spec.tooth_count)) / cos_m + ball

    return {
        "kind": "helical_involute_gear",
        "normal_module_mm": module_n,
        "transverse_module_mm": round(spec.module_transverse_mm, 6),
        "tooth_count": spec.tooth_count,
        "helix_angle_deg": spec.helix_angle_deg,
        "pressure_angle_normal_deg": spec.pressure_angle_normal_deg,
        "virtual_tooth_count": round(virtual_teeth, 4),
        "pitch_diameter_mm": round(2.0 * spec.pitch_radius_mm, 4),
        "base_diameter_mm": round(2.0 * spec.base_radius_mm, 4),
        "tip_diameter_mm": round(2.0 * spec.outer_radius_mm, 4),
        "root_diameter_mm": round(2.0 * spec.root_radius_mm, 4),
        "normal_span_measurement": {
            "k": k,
            "span_length_mm": round(span_length, 4),
            "span_rule": "k = round(z_v·α_n/180° + 0.5), z_v = z/cos³β",
        },
        "span_over_balls": {
            "ball_diameter_mm": round(ball, 4),
            "alpha_M_deg": round(math.degrees(alpha_m), 4),
            "span_mm": round(span, 4),
            "even_teeth": spec.tooth_count % 2 == 0,
        },
        "measurement_note": "公法线沿法向量；跨棒距用量球（量柱会沿螺旋面滑）",
    }

def external_gear_inspection(spec: InvoluteGearSpec,
                             pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """外齿轮一整套检验尺寸（出图/检验用）。"""
    return {
        "kind": "external_involute_gear",
        "module_mm": spec.module_mm,
        "tooth_count": spec.tooth_count,
        "profile_shift_x": getattr(spec, "profile_shift_x", 0.0),
        "pitch_diameter_mm": round(2.0 * spec.pitch_radius_mm, 4),
        "base_diameter_mm": round(2.0 * spec.base_radius_mm, 4),
        "tip_diameter_mm": round(2.0 * spec.outer_radius_mm, 4),
        "root_diameter_mm": round(2.0 * spec.root_radius_mm, 4),
        "tooth_thickness_at_pitch_mm": round(tooth_thickness_at_pitch(spec), 4),
        "span_measurement": span_measurement(spec),
        "span_over_pins": span_over_pins(spec, pin_diameter_mm),
    }


def internal_gear_inspection(spec: InternalGearSpec,
                             pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """内齿圈检验尺寸（内齿的跨棒距要减量柱，符号与外齿相反）。"""
    return {
        "kind": "internal_involute_gear",
        "module_mm": spec.module_mm,
        "tooth_count": spec.tooth_count,
        "profile_shift_x": spec.profile_shift_x,
        "pitch_diameter_mm": round(2.0 * spec.pitch_radius_mm, 4),
        "base_diameter_mm": round(2.0 * spec.base_radius_mm, 4),
        "tip_diameter_mm": round(2.0 * spec.tip_radius_mm, 4),
        "root_diameter_mm": round(2.0 * spec.root_radius_mm, 4),
        "space_width_at_pitch_mm": round(
            spec.module_mm * math.pi / 2.0, 4),
        "span_over_pins": span_over_pins_internal(spec, pin_diameter_mm),
    }
