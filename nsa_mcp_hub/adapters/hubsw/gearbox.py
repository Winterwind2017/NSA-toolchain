"""两级平行轴圆柱齿轮减速器（结构示意级）的 Feature Graph。

设计取舍：**不追求齿面精度，追求"整机一次成型"**——每个齿轮用"四顶点/齿"
的结构化梯形轮廓（分度圆上齿宽 48%、齿顶宽 24% 的近似），这样一张草图
就能把整圈齿画完，拉伸即得齿轮体；再补三根轴与三处键槽，16 个特征构成
一个可用于布置/干涉/传动比校核的整机模型。

两级中心距按标准齿轮公式 ``a = m(z1+z2)/2``；第二级整体沿轴向偏置
``齿轮厚 + 轴向间隙``，避免两级在同一平面里打架。
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import ContractError, require_positive
from .involute_gear import InvoluteGearSpec, validate_gear_spec


def structural_gear_outline(spec: InvoluteGearSpec,
                            center: tuple[float, float]) -> list[list[float]]:
    """整圈齿轮轮廓：每齿四个顶点（齿根-齿顶-齿顶-齿根），闭合折线。"""
    cx, cy = center
    pitch_angle = 2.0 * math.pi / spec.tooth_count
    root_half = pitch_angle * 0.46
    tip_half = pitch_angle * 0.24

    points: list[list[float]] = []
    for index in range(spec.tooth_count):
        base_angle = index * pitch_angle
        for radius, delta in (
            (spec.root_radius_mm, -root_half),
            (spec.outer_radius_mm, -tip_half),
            (spec.outer_radius_mm, tip_half),
            (spec.root_radius_mm, root_half),
        ):
            angle = base_angle + delta
            points.append([cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle)])
    return points


def _gear_features(prefix: str, center: tuple[float, float], plane: str,
                   spec: InvoluteGearSpec) -> list[dict[str, Any]]:
    """一个齿轮 = 一张草图（齿形 + 轴孔）+ 一次拉伸。"""
    return [
        {
            "name": f"{prefix}Sketch",
            "kind": "sketch",
            "plane": plane,
            "entities": [
                {"kind": "polyline", "closed": True,
                 "points": structural_gear_outline(spec, center)},
                {"kind": "circle", "center": [center[0], center[1]],
                 "radius_mm": spec.bore_diameter_mm / 2.0},
            ],
        },
        {
            "name": prefix,
            "kind": "boss_extrude",
            "sketch": f"{prefix}Sketch",
            "depth_mm": spec.thickness_mm,
            "merge": False,
        },
    ]


def keyway_rectangle(center_x: float, shaft_diameter: float,
                     width: float, depth: float) -> dict[str, Any]:
    """轴顶开一个矩形键槽（从 r 切到 r-depth）。"""
    radius = shaft_diameter / 2.0
    return {
        "kind": "polyline",
        "closed": True,
        "points": [
            [center_x - width / 2.0, radius - depth],
            [center_x + width / 2.0, radius - depth],
            [center_x + width / 2.0, radius],
            [center_x - width / 2.0, radius],
        ],
    }


def build_two_stage_reducer_graph(
    *,
    module_mm: float = 2.0,
    pressure_angle_deg: float = 20.0,
    stage1_teeth: tuple[int, int] = (20, 40),
    stage2_teeth: tuple[int, int] = (20, 60),
    gear_thickness_mm: float = 10.0,
    axial_gap_mm: float = 8.0,
    bore_diameters_mm: tuple[float, float, float] = (10.0, 12.0, 14.0),
    radial_clearance_mm: float = 0.1,
    shaft_extension_mm: float = 5.0,
) -> dict[str, Any]:
    """生成 16 个特征的整机图（4 基准/新建 + 4 齿轮×2 + 4 轴与键槽）。"""
    module = require_positive(module_mm, "module_mm")
    thickness = require_positive(gear_thickness_mm, "gear_thickness_mm")
    gap = require_positive(axial_gap_mm, "axial_gap_mm")
    clearance = require_positive(radial_clearance_mm, "radial_clearance_mm")
    extension = require_positive(shaft_extension_mm, "shaft_extension_mm")

    if len(stage1_teeth) != 2 or len(stage2_teeth) != 2:
        raise ContractError("each stage must contain a pinion and a driven gear")
    if len(bore_diameters_mm) != 3:
        raise ContractError("bore_diameters_mm must contain input, intermediate, output")

    z1, z2 = (int(value) for value in stage1_teeth)
    z3, z4 = (int(value) for value in stage2_teeth)
    bore_input, bore_intermediate, bore_output = (
        require_positive(value, "bore_diameters_mm") for value in bore_diameters_mm
    )

    common = {
        "module_mm": module,
        "pressure_angle_deg": pressure_angle_deg,
        "thickness_mm": thickness,
        "root_fillet_mm": min(0.45, module * 0.225),
        "tip_chamfer_mm": min(0.25, module * 0.125),
    }
    specs = [
        validate_gear_spec(tooth_count=z1, bore_diameter_mm=bore_input, **common),
        validate_gear_spec(tooth_count=z2, bore_diameter_mm=bore_intermediate, **common),
        validate_gear_spec(tooth_count=z3, bore_diameter_mm=bore_intermediate, **common),
        validate_gear_spec(tooth_count=z4, bore_diameter_mm=bore_output, **common),
    ]

    center1 = module * (z1 + z2) / 2.0
    center2 = module * (z3 + z4) / 2.0
    centers = [
        (0.0, 0.0),
        (center1, 0.0),
        (center1, 0.0),
        (center1 + center2, 0.0),
    ]

    stage2_offset = thickness + gap
    shaft_length = stage2_offset + thickness + extension
    shaft_diameters = [
        bore_input - 2.0 * clearance,
        bore_intermediate - 2.0 * clearance,
        bore_output - 2.0 * clearance,
    ]
    if any(value <= 0.0 for value in shaft_diameters):
        raise ContractError("radial clearance leaves a non-positive shaft diameter")

    features: list[dict[str, Any]] = [
        {"name": "TwoStageReducer", "kind": "new_part",
         "title": "Two Stage Reducer Gearset"},
        # GB 模板的 Right Plane 法向指向草图 -X，所以模型空间 X 要取负
        {"name": "IntermediateAxisPlane", "kind": "reference_plane_offset",
         "base_plane": "Right Plane", "offset_mm": -center1},
        {"name": "OutputAxisPlane", "kind": "reference_plane_offset",
         "base_plane": "Right Plane", "offset_mm": -(center1 + center2)},
        {"name": "Stage2Plane", "kind": "reference_plane_offset",
         "base_plane": "Front Plane", "offset_mm": -stage2_offset},
    ]
    features += _gear_features("Stage1InputGear", centers[0], "Front Plane", specs[0])
    features += _gear_features("Stage1DrivenGear", centers[1], "Front Plane", specs[1])
    features += _gear_features("Stage2Pinion", centers[2], "Stage2Plane", specs[2])
    features += _gear_features("Stage2OutputGear", centers[3], "Stage2Plane", specs[3])
    features += [
        {
            "name": "ReducerShaftSketch",
            "kind": "sketch",
            "plane": "Front Plane",
            "entities": [
                {"kind": "circle", "center": [center[0], center[1]],
                 "radius_mm": diameter / 2.0}
                for center, diameter in zip(
                    (centers[0], centers[1], centers[3]), shaft_diameters)
            ],
        },
        {"name": "ReducerShafts", "kind": "boss_extrude",
         "sketch": "ReducerShaftSketch", "depth_mm": shaft_length, "merge": False},
        {
            "name": "ReducerKeywaySketch",
            "kind": "sketch",
            "plane": "Front Plane",
            "entities": [
                keyway_rectangle(centers[0][0], shaft_diameters[0], 3.0, 1.6),
                keyway_rectangle(centers[1][0], shaft_diameters[1], 4.0, 2.0),
                keyway_rectangle(centers[3][0], shaft_diameters[2], 5.0, 2.5),
            ],
        },
        {"name": "ReducerKeywayCut", "kind": "cut_extrude",
         "sketch": "ReducerKeywaySketch", "through_all": True},
    ]

    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": "two_stage_parallel_shaft_reducer",
            "module_mm": module,
            "pressure_angle_deg": pressure_angle_deg,
            "stage1_teeth": [z1, z2],
            "stage2_teeth": [z3, z4],
            "stage1_ratio": z2 / z1,
            "stage2_ratio": z4 / z3,
            "total_ratio": (z2 / z1) * (z4 / z3),
            "stage1_center_distance_mm": center1,
            "stage2_center_distance_mm": center2,
            "stage2_axial_offset_mm": stage2_offset,
            "shaft_diameters_mm": shaft_diameters,
            "body_count_expected": 7,
            "tooth_geometry": "structural trapezoidal outline, four vertices per tooth",
        },
        "features": features,
    }
