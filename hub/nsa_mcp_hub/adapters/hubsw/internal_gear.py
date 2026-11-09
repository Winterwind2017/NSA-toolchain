"""内齿轮（内齿圈）：几何计算 + Feature Graph。

内齿轮的齿朝**内**长：齿顶圆在分度圆内侧 ``ra = r − m(1 − x)``，齿根圆在外侧
``rf = r + m(1.25 + x)``，整体是一个"外圆环形 + 内侧齿形"的截面。

**齿形用真渐开线**：内齿圈上开出来的是"齿槽"，标准齿轮的齿槽在分度圆上的弧齿厚
也是 ``πm/2``，所以齿槽两侧就是同一族的渐开线，只是角度关系带负号——

    θ(r) = π/(2z) + inv(α_p) − inv(α_r)        （r 从齿顶 ra 走到齿根 rf）

θ 是齿槽在半径 r 处的**半角**。半径越大 θ 越小：齿槽在根部变窄、在齿顶变宽，
于是内齿的齿是"根宽顶窄"，与啮合事实一致（外齿轮的齿正好相反）。
齿顶低于基圆时（小齿数内齿的常见情形），基圆以下用径向直线补齐。

截面 = 外圆（轮缘）+ 内齿槽轮廓，一次拉伸即得内齿圈：3 个特征。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import ContractError, require_positive
from .involute_gear import involute_angle

#: 齿槽轮廓采样：每侧齿面点数、每段圆弧点数
FLANK_SAMPLES = 8
ARC_SAMPLES = 4


@dataclass
class InternalGearSpec:
    """内齿圈的全部几何量（mm / 度）。"""

    module_mm: float
    tooth_count: int
    pressure_angle_deg: float
    thickness_mm: float
    rim_outer_diameter_mm: float
    profile_shift_x: float
    pitch_radius_mm: float
    base_radius_mm: float
    tip_radius_mm: float      # 齿顶（朝内）
    root_radius_mm: float     # 齿根（朝外）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_internal_gear_spec(
    *,
    module_mm: float,
    tooth_count: int,
    pressure_angle_deg: float,
    thickness_mm: float,
    rim_outer_diameter_mm: float,
    profile_shift_x: float = 0.0,
) -> InternalGearSpec:
    """校验参数并算出四个特征圆；轮缘壁厚不足或齿顶越过基圆都会被拒绝。"""
    module = require_positive(module_mm, "module_mm")
    angle = require_positive(pressure_angle_deg, "pressure_angle_deg")
    thickness = require_positive(thickness_mm, "thickness_mm")
    rim_outer = require_positive(rim_outer_diameter_mm, "rim_outer_diameter_mm")

    if not isinstance(tooth_count, int) or isinstance(tooth_count, bool):
        raise ContractError("tooth_count must be an integer")
    if not 12 <= tooth_count <= 200:
        raise ContractError("tooth_count must be an integer from 12 to 200")
    if not 14.5 <= angle <= 30.0:
        raise ContractError("pressure_angle_deg must be from 14.5 to 30 degrees")
    try:
        shift = float(profile_shift_x)
    except (TypeError, ValueError) as exc:
        raise ContractError("profile_shift_x must be a number") from exc
    if not -0.8 <= shift <= 1.0:
        raise ContractError("profile_shift_x must be within -0.8 .. 1.0")

    pitch = module * tooth_count / 2.0
    base = pitch * math.cos(math.radians(angle))
    tip = pitch - (1.0 - shift) * module
    root = pitch + (1.25 + shift) * module

    if rim_outer / 2.0 <= root + module:
        raise ContractError(
            "rim_outer_diameter_mm 太小：轮缘壁厚至少需要一个模数")

    return InternalGearSpec(
        module_mm=module,
        tooth_count=tooth_count,
        pressure_angle_deg=angle,
        thickness_mm=thickness,
        rim_outer_diameter_mm=rim_outer,
        profile_shift_x=shift,
        pitch_radius_mm=pitch,
        base_radius_mm=base,
        tip_radius_mm=tip,
        root_radius_mm=root,
    )


def space_half_angle(spec: InternalGearSpec, radius: float) -> float:
    """半径处齿槽的半角（内齿：半径越大，齿槽越窄）。"""
    base_pitch_half = math.pi / (2.0 * spec.tooth_count)
    inv_pitch = involute_angle(spec.pitch_radius_mm, spec.base_radius_mm)
    if radius <= spec.base_radius_mm:
        # 基圆以内渐开线无定义：按基圆处的角度取径向直线
        return base_pitch_half + inv_pitch
    return base_pitch_half + inv_pitch - involute_angle(radius, spec.base_radius_mm)


def internal_space_outline(
    spec: InternalGearSpec,
    *,
    flank_samples: int = FLANK_SAMPLES,
    arc_samples: int = ARC_SAMPLES,
) -> list[list[float]]:
    """内齿圈的**内轮廓**（齿槽 + 齿顶）闭合折线。

    遍历次序（整圈一圈到底）：以每个齿槽中心 ``s`` 为起点，

    1. 齿根圆弧：半径 ``rf``（齿槽底），从 ``s − θ_root`` 到 ``s + θ_root``
    2. 右侧齿面：半径 ``rf → ra``，角度 ``s + θ(r)``（渐开线）
    3. 齿顶圆弧：半径 ``ra``，从 ``s + θ_tip`` 跨过齿中心到 ``s + pitch − θ_tip``
    4. 左侧齿面：半径 ``ra → rf``，角度 ``s + pitch − θ(r)``

    下一步正好接下一个齿槽的齿根圆弧，因此整条折线首尾相接、不自交。
    """
    if flank_samples < 3 or arc_samples < 2:
        raise ContractError("flank_samples >= 3 and arc_samples >= 2 are required")

    pitch_angle = 2.0 * math.pi / spec.tooth_count
    tip_r = spec.tip_radius_mm
    root_r = spec.root_radius_mm

    theta_tip = space_half_angle(spec, tip_r)
    theta_root = space_half_angle(spec, root_r)
    half_pitch = pitch_angle / 2.0
    if theta_tip >= half_pitch:
        raise ContractError(
            "齿槽在齿顶处互相侵占（z 太小或变位过大）：请增大齿数或调整变位系数")
    if theta_root <= 0.0:
        raise ContractError("齿槽在齿根处已闭合（齿根圆过大）：请检查变位系数")

    # 齿面半径：从齿根走到齿顶（渐开线在基圆以下退化为径向直线）
    flank_radii = [root_r + (tip_r - root_r) * index / (flank_samples - 1)
                   for index in range(flank_samples)]

    def polar(radius: float, angle: float) -> list[float]:
        return [radius * math.cos(angle), radius * math.sin(angle)]

    points: list[list[float]] = []
    for index in range(spec.tooth_count):
        center = (index + 0.5) * pitch_angle

        # 1) 齿根圆弧（齿槽底）
        for step in range(arc_samples + 1):
            angle = center - theta_root + 2.0 * theta_root * step / arc_samples
            points.append(polar(root_r, angle))

        # 2) 右侧齿面：齿根 → 齿顶
        for radius in flank_radii:
            points.append(polar(radius, center + space_half_angle(spec, radius)))

        # 3) 齿顶圆弧：跨过一个齿
        tip_from = center + theta_tip
        tip_to = center + pitch_angle - theta_tip
        for step in range(1, arc_samples + 1):
            angle = tip_from + (tip_to - tip_from) * step / arc_samples
            points.append(polar(tip_r, angle))

        # 4) 左侧齿面：齿顶 → 齿根（下一齿槽的左侧）
        for radius in reversed(flank_radii):
            points.append(polar(radius, center + pitch_angle
                                - space_half_angle(spec, radius)))

    # 相邻段在接缝处会重复同一点，去掉，避免草图出现零长度线段
    cleaned: list[list[float]] = []
    for point in points:
        if not cleaned or abs(point[0] - cleaned[-1][0]) > 1e-9                 or abs(point[1] - cleaned[-1][1]) > 1e-9:
            cleaned.append(point)
    if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) < 1e-9             and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-9:
        cleaned.pop()
    return cleaned


def _polygon_area(points: list[list[float]]) -> float:
    """鞋带公式（有向面积为负也照算绝对值）。"""
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def build_internal_gear_graph(spec: InternalGearSpec) -> dict[str, Any]:
    """3 个特征：新建零件 → 截面草图（轮缘圆 + 内齿轮廓）→ 拉伸。"""
    rim_radius = spec.rim_outer_diameter_mm / 2.0
    inner = internal_space_outline(spec)
    ring_area = math.pi * rim_radius ** 2 - _polygon_area(inner)

    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": "internal_ring_gear",
            "gear_spec": spec.to_dict(),
            "tip_above_base": spec.tip_radius_mm > spec.base_radius_mm,
            "ring_area_mm2": round(ring_area, 3),
            "expected_volume_mm3": round(ring_area * spec.thickness_mm, 3),
            "tooth_geometry": "true involute space profile (tip inward)",
            "space_half_angle_at_tip_deg": round(
                math.degrees(space_half_angle(spec, spec.tip_radius_mm)), 4),
            "space_half_angle_at_root_deg": round(
                math.degrees(space_half_angle(spec, spec.root_radius_mm)), 4),
        },
        "features": [
            {"name": "InternalRing", "kind": "new_part", "title": "Internal Ring Gear"},
            {
                "name": "RingSectionSketch",
                "kind": "sketch",
                "plane": "Front Plane",
                "entities": [
                    {"kind": "circle", "center": [0.0, 0.0], "radius_mm": rim_radius},
                    {"kind": "polyline", "closed": True, "points": inner},
                ],
            },
            {
                "name": "RingBoss",
                "kind": "boss_extrude",
                "sketch": "RingSectionSketch",
                "depth_mm": spec.thickness_mm,
            },
        ],
    }
