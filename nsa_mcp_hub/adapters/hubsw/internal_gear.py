"""内齿轮（内齿圈）：几何计算 + Feature Graph。

内齿轮的齿朝**内**长：齿顶圆在分度圆内侧 ``ra = r − m(1 − x)``，齿根圆在外侧
``rf = r + m(1.25 + x)``，整体是一个"外圆环形 + 内侧齿形"的截面。

几何取舍（写在明处）：齿形用**结构梯形**（每齿四顶点），不做渐开线逼近。
理由是内齿圈的渐开线要按"齿槽包络"反求，属于刀具/啮合仿真范畴；而这里要的是
**可用于布置、干涉、壁厚校核的环体**。齿顶/齿根/基圆按标准公式给，能对得上
齿轮基本参数；需要切齿精度时另行按刀具包络生成。

截面 = 外圆（轮缘）+ 内侧齿形轮廓，一次拉伸即得内齿圈：3 个特征。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import ContractError, require_positive

#: 结构齿形的角度分配（占单齿节距的比例）
ROOT_HALF_RATIO = 0.46
TIP_HALF_RATIO = 0.24


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


def internal_tooth_outline(spec: InternalGearSpec,
                           samples_per_tooth: int = 4) -> list[list[float]]:
    """内齿圈的闭合内轮廓：每齿四顶点，齿顶朝圆心。"""
    if samples_per_tooth < 4:
        raise ContractError("samples_per_tooth must be at least 4")
    pitch_angle = 2.0 * math.pi / spec.tooth_count
    root_half = pitch_angle * ROOT_HALF_RATIO
    tip_half = pitch_angle * TIP_HALF_RATIO

    points: list[list[float]] = []
    for index in range(spec.tooth_count):
        center = index * pitch_angle
        for radius, delta in (
            (spec.root_radius_mm, -root_half),
            (spec.tip_radius_mm, -tip_half),
            (spec.tip_radius_mm, tip_half),
            (spec.root_radius_mm, root_half),
        ):
            angle = center + delta
            points.append([radius * math.cos(angle), radius * math.sin(angle)])
    return points


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
    inner = internal_tooth_outline(spec)
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
            "tooth_geometry": "structural trapezoid (four vertices per tooth, tip inward)",
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
