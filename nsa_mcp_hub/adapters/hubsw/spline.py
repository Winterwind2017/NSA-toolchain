"""矩形花键轴（GB/T 1144 系列）：几何计算 + Feature Graph。

矩形花键的齿侧是**直的**、且等宽（宽度 = 键宽 b），所以轮廓可以精确画出来，
不像渐开线那样需要近似：

* 外径 ``D``、内径 ``d``、齿数 ``z``、键宽 ``b``
* 每个齿在外圆上的半角 ``asin(b / D)``，在内圆上的半角 ``asin(b / d)``
* 齿侧用直线连接对应角点 —— 这就是标准矩形花键的截面

一次"草图 + 拉伸"即可：3 个特征。面积用鞋带公式算，写进 metadata 供体积判据用。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import ContractError, require_positive


@dataclass
class SplineSpec:
    outer_diameter_mm: float
    inner_diameter_mm: float
    tooth_count: int
    key_width_mm: float
    length_mm: float
    outer_half_angle_rad: float
    inner_half_angle_rad: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_spline_spec(
    *,
    outer_diameter_mm: float,
    inner_diameter_mm: float,
    tooth_count: int,
    key_width_mm: float,
    length_mm: float,
) -> SplineSpec:
    """校验并算出齿侧两侧的半角。"""
    outer = require_positive(outer_diameter_mm, "outer_diameter_mm")
    inner = require_positive(inner_diameter_mm, "inner_diameter_mm")
    width = require_positive(key_width_mm, "key_width_mm")
    length = require_positive(length_mm, "length_mm")

    if inner >= outer:
        raise ContractError("inner_diameter_mm must be smaller than outer_diameter_mm")
    if not isinstance(tooth_count, int) or isinstance(tooth_count, bool):
        raise ContractError("tooth_count must be an integer")
    if not 4 <= tooth_count <= 40:
        raise ContractError("tooth_count must be an integer from 4 to 40")
    if width >= inner:
        raise ContractError("key_width_mm must be smaller than inner_diameter_mm")

    # 齿侧直线：外圆与内圆上同宽 b 的两点，各自对应一个中心半角
    outer_half = math.asin(min(1.0, width / outer))
    inner_half = math.asin(min(1.0, width / inner))
    pitch_angle = math.pi / tooth_count
    if inner_half >= pitch_angle:
        raise ContractError(
            "key_width_mm 相对内径太大：内圆上的齿侧角超过了半个节距，齿廓会自交")

    return SplineSpec(
        outer_diameter_mm=outer,
        inner_diameter_mm=inner,
        tooth_count=tooth_count,
        key_width_mm=width,
        length_mm=length,
        outer_half_angle_rad=outer_half,
        inner_half_angle_rad=inner_half,
    )


def spline_outline(spec: SplineSpec) -> list[list[float]]:
    """整圈矩形花键轮廓：每齿"外圆弧 → 齿侧 → 内圆弧 → 齿侧"。"""
    outer_r = spec.outer_diameter_mm / 2.0
    inner_r = spec.inner_diameter_mm / 2.0
    step = 2.0 * math.pi / spec.tooth_count
    gap_half = step / 2.0 - spec.inner_half_angle_rad   # 相邻齿之间内圆弧的半角
    points: list[list[float]] = []

    for index in range(spec.tooth_count):
        center = index * step
        # 外圆弧（齿顶）：从 -outer_half 到 +outer_half
        points.append([outer_r * math.cos(center - spec.outer_half_angle_rad),
                       outer_r * math.sin(center - spec.outer_half_angle_rad)])
        points.append([outer_r * math.cos(center + spec.outer_half_angle_rad),
                       outer_r * math.sin(center + spec.outer_half_angle_rad)])
        # 齿侧下行到内圆
        points.append([inner_r * math.cos(center + spec.inner_half_angle_rad),
                       inner_r * math.sin(center + spec.inner_half_angle_rad)])
        # 内圆弧（齿槽底）：走到下一个齿的起点
        points.append([inner_r * math.cos(center + spec.inner_half_angle_rad + 2 * gap_half),
                       inner_r * math.sin(center + spec.inner_half_angle_rad + 2 * gap_half)])
    return points


def _polygon_area(points: list[list[float]]) -> float:
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _flank_line(spec: SplineSpec, tooth_index: int) -> tuple[list[float], list[float]]:
    """某个齿**右侧**齿侧直线的两个端点（外径 → 内径）。"""
    step = 2.0 * math.pi / spec.tooth_count
    center = tooth_index * step
    outer_r = spec.outer_diameter_mm / 2.0
    inner_r = spec.inner_diameter_mm / 2.0
    p_out = [outer_r * math.cos(center + spec.outer_half_angle_rad),
             outer_r * math.sin(center + spec.outer_half_angle_rad)]
    p_in = [inner_r * math.cos(center + spec.inner_half_angle_rad),
            inner_r * math.sin(center + spec.inner_half_angle_rad)]
    return p_out, p_in


def _distance_to_line(point: list[float], a: list[float], b: list[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    return abs(dx * (point[1] - a[1]) - dy * (point[0] - a[0])) / length


def pin_contact_radius(spec: SplineSpec, pin_diameter_mm: float) -> tuple[float, str]:
    """量柱同时贴住某个齿槽两侧齿侧时的中心半径。

    返回 ``(半径, 接触方式)``：``flank`` = 被两侧齿侧夹住（正常）；``root`` = 量柱
    太小、一直落到齿根圆上（量不到齿厚，属于**量具选小了**）。
    齿槽外宽内窄，所以"离齿侧的距离"随半径单调增，二分很稳。
    """
    if pin_diameter_mm <= 0.0:
        raise ContractError("pin_diameter_mm must be positive")
    radius_pin = pin_diameter_mm / 2.0
    bisector = math.pi / spec.tooth_count          # 齿槽中心线角度
    a, b = _flank_line(spec, 0)
    inner_radius = spec.inner_diameter_mm / 2.0

    def gap(center_radius: float) -> float:
        point = [center_radius * math.cos(bisector),
                 center_radius * math.sin(bisector)]
        return _distance_to_line(point, a, b) - radius_pin

    if gap(inner_radius) >= 0.0:
        # 量柱比齿槽底还窄：直接落底，量不到齿厚
        return inner_radius + radius_pin, "root"

    high = spec.outer_diameter_mm / 2.0 + pin_diameter_mm
    if gap(high) <= 0.0:
        raise ContractError("量柱过大：推到齿顶以外仍碰不到齿侧")
    low = inner_radius
    for _ in range(80):
        middle = 0.5 * (low + high)
        if gap(middle) > 0.0:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high), "flank"


def _probe(spec: SplineSpec, pin_diameter_mm: float):
    """返回 (中心半径, 接触方式) 或 None（量柱放不进齿槽）。"""
    try:
        return pin_contact_radius(spec, pin_diameter_mm)
    except ContractError:
        return None


def flank_transition_pin(spec: SplineSpec) -> float:
    """齿槽从"量柱落底"过渡到"夹在齿侧"的临界量柱直径。

    小于它，量柱沉到齿根圆上（量不到齿厚）；大于它才会被两侧齿侧夹住。
    """
    low, high = 1e-3, spec.outer_diameter_mm
    for _ in range(60):
        if _probe(spec, high) is not None:
            break
        high *= 0.5
    else:
        raise ContractError("反算量柱失败：齿槽容不下任何量柱")
    for _ in range(80):
        middle = 0.5 * (low + high)
        probe = _probe(spec, middle)
        if probe is None or probe[1] == "root":
            low = middle
        else:
            high = middle
    return high


def recommended_pin_diameter(spec: SplineSpec) -> float:
    """推荐量柱直径：在**齿侧接触**的分支上，让量柱中心尽量落在齿高中部半径。

    花键的"齿高中部"指**径向**中径 ``(d + D)/2 / 2``。直齿侧上如果该半径还
    未脱离"落底"区，就取临界量柱（``flank_transition_pin``）——此时量柱同时
    贴住两侧齿侧与齿根，是这条齿槽能用的最细量具。
    """
    transition = flank_transition_pin(spec)
    target = 0.5 * (spec.inner_diameter_mm + spec.outer_diameter_mm) / 2.0
    probe = _probe(spec, transition)
    start_radius = probe[0] if probe else 0.0
    if start_radius >= target:              # 已经在中径以外：取临界量柱
        return round(transition, 3)

    low, high = transition, spec.outer_diameter_mm
    for _ in range(80):
        middle = 0.5 * (low + high)
        result = _probe(spec, middle)
        if result is None or result[0] > target:
            high = middle
        else:
            low = middle
    return round(0.5 * (low + high), 3)


def span_over_pins(spec: SplineSpec, pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """外花键跨棒距 M：量柱放在**相对**的两个齿槽里量。"""
    pin = float(pin_diameter_mm) if pin_diameter_mm else recommended_pin_diameter(spec)
    if pin <= 0.0:
        raise ContractError("pin_diameter_mm must be positive")
    radius, contact = pin_contact_radius(spec, pin)
    if spec.tooth_count % 2 == 0:
        span = 2.0 * radius + pin
    else:
        span = 2.0 * radius * math.cos(math.pi / (2.0 * spec.tooth_count)) + pin
    return {
        "pin_diameter_mm": round(pin, 4),
        "pin_diameter_rule": ("flank contact at radial mid height"
                              if not pin_diameter_mm else "caller-specified"),
        "pin_contact_radius_mm": round(radius, 4),
        "mid_tooth_height_radius_mm": round(
            0.5 * (spec.inner_diameter_mm + spec.outer_diameter_mm) / 2.0, 4),
        "span_mm": round(span, 4),
        "even_teeth": spec.tooth_count % 2 == 0,
        "contact": contact,
    }


def spline_inspection(spec: SplineSpec,
                      pin_diameter_mm: float | None = None) -> dict[str, Any]:
    """矩形花键检验尺寸：齿厚、齿槽宽、量柱直径与跨棒距。"""
    pitch_diameter = (spec.outer_diameter_mm + spec.inner_diameter_mm) / 2.0
    space_width = (math.pi * pitch_diameter / spec.tooth_count
                   - spec.key_width_mm)
    return {
        "kind": "rectangular_spline",
        "standard": "GB/T 1144",
        "outer_diameter_mm": spec.outer_diameter_mm,
        "inner_diameter_mm": spec.inner_diameter_mm,
        "tooth_count": spec.tooth_count,
        "key_width_mm": spec.key_width_mm,
        "tooth_thickness_mm": spec.key_width_mm,
        "space_width_at_pitch_mm": round(space_width, 4),
        "recommended_pin_diameter_mm": recommended_pin_diameter(spec),
        "span_over_pins": span_over_pins(spec, pin_diameter_mm),
    }


def build_spline_shaft_graph(spec: SplineSpec) -> dict[str, Any]:
    """3 个特征：新建零件 → 花键截面 → 拉伸成轴。"""
    outline = spline_outline(spec)
    area = _polygon_area(outline)
    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": "rectangular_spline_shaft",
            "spline_spec": spec.to_dict(),
            "standard": "GB/T 1144",
            "section_area_mm2": round(area, 3),
            "expected_volume_mm3": round(area * spec.length_mm, 3),
        },
        "features": [
            {"name": "SplineShaft", "kind": "new_part", "title": "Rectangular Spline Shaft"},
            {
                "name": "SplineSectionSketch",
                "kind": "sketch",
                "plane": "Front Plane",
                "entities": [{"kind": "polyline", "closed": True, "points": outline}],
            },
            {
                "name": "SplineBoss",
                "kind": "boss_extrude",
                "sketch": "SplineSectionSketch",
                "depth_mm": spec.length_mm,
            },
        ],
    }
