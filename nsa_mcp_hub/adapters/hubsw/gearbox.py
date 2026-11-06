"""两级平行轴圆柱齿轮减速器（结构示意级）的 Feature Graph。

齿形：**真渐开线**（复用 `involute_gear.tooth_outline_points`，与单件齿轮、
斜齿轮同一套点），每齿一条离散渐开线折线，齿根弧自然相接；整圈一张草图，
拉伸即得齿轮体。再补三根轴与三处键槽，16 个特征构成一个可用于布置/干涉/
传动比校核的整机模型。

两级中心距按标准齿轮公式 ``a = m(z1+z2)/2``；第二级整体沿轴向偏置
``齿轮厚 + 轴向间隙``，避免两级在同一平面里打架。
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import ContractError, require_positive
from .gear_inspection import external_gear_inspection
from .keyways import key_for_shaft, standard_length
from .involute_gear import (InvoluteGearSpec, tooth_outline_points,
                            validate_gear_spec)


def involute_gear_outline(
    spec: InvoluteGearSpec,
    center: tuple[float, float],
    *,
    samples_per_flank: int = 8,
    samples_across_tip: int = 3,
) -> list[list[float]]:
    """整圈渐开线齿轮轮廓（平移到 ``center``），闭合折线。

    每个齿用 :func:`tooth_outline_points` 生成（齿根 → 齿面 → 齿顶弧 → 齿面），
    相邻齿之间靠齿根弦相接；比"四顶点梯形"多花一些点，但齿形是真渐开线，
    啮合、干涉与齿厚都可以直接对表。
    """
    cx, cy = center
    pitch_angle = 2.0 * math.pi / spec.tooth_count
    shift = getattr(spec, "profile_shift_x", 0.0)
    points: list[list[float]] = []
    for index in range(spec.tooth_count):
        tooth = tooth_outline_points(
            pitch_radius_mm=spec.pitch_radius_mm,
            base_radius_mm=spec.base_radius_mm,
            root_radius_mm=spec.root_radius_mm,
            outer_radius_mm=spec.outer_radius_mm,
            tooth_count=spec.tooth_count,
            rotation_rad=index * pitch_angle,
            samples_per_flank=samples_per_flank,
            samples_across_tip=samples_across_tip,
            profile_shift_x=shift,
            pressure_angle_deg=spec.pressure_angle_deg,
        )
        points.extend([[cx + x, cy + y] for x, y in tooth])
    return points


def structural_gear_outline(
    spec: InvoluteGearSpec,
    center: tuple[float, float],
) -> list[list[float]]:
    """兼容旧名：现在返回的是**渐开线**轮廓（不再是对称梯形）。"""
    return involute_gear_outline(spec, center)


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
                 "points": involute_gear_outline(spec, center)},
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

    # 键与键槽按轴径查 GB/T 1096：b×h、轴槽深 t1、毂槽深 t2、标准键长
    try:
        shaft_keyways = [key_for_shaft(diameter) for diameter in shaft_diameters]
    except ContractError as exc:
        raise ContractError("轴径查不到标准平键：%s" % exc) from exc
    key_length = standard_length(thickness)
    for spec_key, diameter in zip(shaft_keyways, shaft_diameters):
        if spec_key.width_mm >= diameter:
            raise ContractError(
                "标准键宽 %.1f 不小于轴径 %.1f：请加大轴径或改用花键"
                % (spec_key.width_mm, diameter))

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
            # 键宽与轴槽深按 GB/T 1096 查表（shaft_keyways 在函数开头算好）
            "entities": [
                keyway_rectangle(centers[0][0], shaft_diameters[0],
                                 shaft_keyways[0].width_mm,
                                 shaft_keyways[0].shaft_depth_mm),
                keyway_rectangle(centers[1][0], shaft_diameters[1],
                                 shaft_keyways[1].width_mm,
                                 shaft_keyways[1].shaft_depth_mm),
                keyway_rectangle(centers[3][0], shaft_diameters[2],
                                 shaft_keyways[2].width_mm,
                                 shaft_keyways[2].shaft_depth_mm),
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
            "tooth_geometry": "true involute outline (shared tooth_outline_points)",
            "keyways": [
                dict(spec.to_dict(), key_length_mm=key_length,
                     shaft_diameter_mm=round(diameter, 3))
                for spec, diameter in zip(shaft_keyways, shaft_diameters)
            ],
            "keyway_standard": "GB/T 1096",
            # 每个齿轮的检验尺寸（公法线/跨棒距），出图时可直接给检验员
            "gear_inspections": [
                dict(external_gear_inspection(spec_gear), label=label)
                for spec_gear, label in zip(
                    specs,
                    ("Stage1InputGear", "Stage1DrivenGear",
                     "Stage2Pinion", "Stage2OutputGear"))
            ],
        },
        "features": features,
    }
