"""输出轴（按《输出轴零件图.DWG》）的 Feature Graph。

轴是"半剖面绕轴芯旋转"做出来的：剖面从轴心出发，沿 X 走完七段台阶，
再回到轴心；两处键槽用偏置基准面上的圆头槽切出；末端还有一个
Ø3 的径向盲孔。总长 333 mm，七段直径 55/60/65/60/55/50/45。
"""

from __future__ import annotations

import math
from typing import Any

#: 七段长度与直径（图纸标注，mm）
SEGMENT_LENGTHS = (46.0, 61.0, 8.0, 53.0, 44.0, 57.0, 64.0)
SEGMENT_DIAMETERS = (55.0, 60.0, 65.0, 60.0, 55.0, 50.0, 45.0)

#: 两处键槽：宽 / 长 / 深 / 轴向起点
KEYWAYS = (
    {"name": "Keyway18", "width_mm": 18.0, "length_mm": 50.0, "depth_mm": 5.5, "start_mm": 52.0},
    {"name": "Keyway14", "width_mm": 14.0, "length_mm": 56.0, "depth_mm": 4.5, "start_mm": 273.0},
)

#: 轴端螺纹孔（M6 底孔）与径向盲孔
CORE_HOLE = {"diameter_mm": 5.0, "depth_mm": 20.0}
RADIAL_HOLE = {"diameter_mm": 3.0, "depth_mm": 12.0, "offset_mm": 12.0}

#: 未注倒角
UNSPECIFIED_CHAMFER_MM = 2.0


def _stations() -> list[float]:
    stations = [0.0]
    for length in SEGMENT_LENGTHS:
        stations.append(stations[-1] + length)
    return stations


def slot_outline(start_mm: float, length_mm: float, width_mm: float,
                 arc_segments: int = 8) -> list[list[float]]:
    """圆头槽的闭合轮廓：两个半圆 + 两条直边，从左侧半圆顶开始逆时针。"""
    radius = width_mm / 2.0
    left_center = start_mm + radius
    right_center = start_mm + length_mm - radius

    points: list[list[float]] = []
    for index in range(arc_segments + 1):
        angle = math.pi / 2.0 + math.pi * index / arc_segments
        points.append([left_center + radius * math.cos(angle),
                       radius * math.sin(angle)])
    for index in range(arc_segments + 1):
        angle = -math.pi / 2.0 + math.pi * index / arc_segments
        points.append([right_center + radius * math.cos(angle),
                       radius * math.sin(angle)])
    return points


def _profile_points() -> list[list[float]]:
    """实心半剖面：单调沿 +X 走完七段台阶，两端各一个倒角。

    必须保证 x 单调不减——一旦回折（例如先到 x=2 又回 x=0），轮廓自交，
    SolidWorks 的旋转会直接建不出特征（实测）。
    """
    stations = _stations()
    radii = [diameter / 2.0 for diameter in SEGMENT_DIAMETERS]
    chamfer = UNSPECIFIED_CHAMFER_MM
    total = stations[-1]

    points: list[list[float]] = [
        [0.0, 0.0],
        [0.0, radii[0] - chamfer],
        [chamfer, radii[0]],
    ]
    for index, radius in enumerate(radii):
        end_x = total - chamfer if index == len(radii) - 1 else stations[index + 1]
        points.append([end_x, radius])
        if index < len(radii) - 1:
            points.append([stations[index + 1], radii[index + 1]])
    points += [
        [total, radii[-1] - chamfer],
        [total, 0.0],
    ]
    return points


def _keyway_features() -> list[dict[str, Any]]:
    """每处键槽三步：偏置基准面 → 槽轮廓草图 → 切除。"""
    features: list[dict[str, Any]] = []
    for keyway in KEYWAYS:
        name = keyway["name"]
        stage = keyway["start_mm"]  # 起点与段界对齐，直接用该处半径做偏置
        features += [
            {
                "name": f"{name}Plane",
                "kind": "reference_plane_offset",
                "base_plane": "Front Plane",
                "offset_mm": 30.0 if name == "Keyway18" else 22.5,
            },
            {
                "name": f"{name}Sketch",
                "kind": "sketch",
                "plane": f"{name}Plane",
                "entities": [{
                    "kind": "polyline",
                    "closed": True,
                    "points": slot_outline(stage, keyway["length_mm"],
                                           keyway["width_mm"]),
                }],
            },
            {
                "name": f"{name}Cut",
                "kind": "cut_extrude",
                "sketch": f"{name}Sketch",
                "depth_mm": keyway["depth_mm"],
                "reverse_direction": False,
            },
        ]
    return features


def build_output_shaft_from_dwg_graph() -> dict[str, Any]:
    """输出轴的 12 个原生特征（旋转 + 两处键槽 + 径向盲孔）。"""
    stations = _stations()
    radial = RADIAL_HOLE

    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "source_drawing": "输出轴零件图.DWG",
            "part_type": "two_stage_reducer_output_shaft",
            "units": "mm",
            "total_length_mm": stations[-1],
            "segment_lengths_mm": list(SEGMENT_LENGTHS),
            "segment_diameters_mm": list(SEGMENT_DIAMETERS),
            "keyways": [dict(item) for item in KEYWAYS],
            "end_holes": [
                {"kind": "M6_thread_core", **CORE_HOLE},
                {"kind": "blind_drill", "radial_offset_mm": radial["offset_mm"],
                 "diameter_mm": radial["diameter_mm"], "depth_mm": radial["depth_mm"]},
            ],
            "unspecified_chamfer_mm": UNSPECIFIED_CHAMFER_MM,
            "unspecified_fillet_mm": 1.2,
        },
        "features": [
            {"name": "OutputShaftPart", "kind": "new_part",
             "title": "Output Shaft from DWG"},
            {
                "name": "OutputShaftProfile",
                "kind": "sketch",
                "plane": "Front Plane",
                "entities": [
                    # 第一段是构造线，兼作旋转轴（实测比"两基准面求交的参考轴"可靠）
                    {"kind": "line", "start": [0.0, 0.0],
                     "end": [_stations()[-1], 0.0], "construction": True},
                    {"kind": "polyline", "closed": True,
                     "points": _profile_points()},
                ],
            },
            {
                "name": "OutputShaftRevolve",
                "kind": "boss_revolve",
                "sketch": "OutputShaftProfile",
                "axis_segment": "Line1",
                "angle_deg": 360.0,
                "merge": True,
            },
            *_keyway_features(),
            {
                "name": "CoreHoleSketch",
                "kind": "sketch",
                "plane": "Right Plane",
                "entities": [{
                    "kind": "circle",
                    "center": [0.0, 0.0],
                    "radius_mm": CORE_HOLE["diameter_mm"] / 2.0,
                }],
            },
            {
                "name": "CoreHoleDia5Depth20",
                "kind": "cut_extrude",
                "sketch": "CoreHoleSketch",
                "depth_mm": CORE_HOLE["depth_mm"],
                "reverse_direction": True,
            },
            {
                "name": "RadialHoleSketch",
                "kind": "sketch",
                "plane": "Right Plane",
                "entities": [{
                    "kind": "circle",
                    "center": [radial["offset_mm"], 0.0],
                    "radius_mm": radial["diameter_mm"] / 2.0,
                }],
            },
            {
                "name": "RadialHoleDia3Depth12",
                "kind": "cut_extrude",
                "sketch": "RadialHoleSketch",
                "depth_mm": radial["depth_mm"],
                "reverse_direction": True,
            },
        ],
    }
