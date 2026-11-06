"""参数化零件生成器：block / cylinder / tube / flange / stepped_shaft。

每个生成器只做一件事——把参数翻译成 Feature Graph IR。所有几何量都从参数
现算，不读模型、不碰 COM，因此可以在没有 SolidWorks 的机器上编译与审计。

参数命名遵循机械制图的习惯（``diameter_mm`` / ``length_mm`` / ``thickness_mm``），
缺省值取常见的结构件尺寸，保证"只给 part_type 也能出一张合理的图"。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .contracts import ContractError, require_positive

#: 支持的五类零件
PART_TYPES = ("block", "cylinder", "tube", "flange", "stepped_shaft")


# ------------------------------------------------------------------ 小工具

def _param(parameters: dict[str, Any], key: str, default: float | None = None) -> float:
    """取一个正数参数（缺省值同样要过校验）。"""
    return require_positive(parameters.get(key, default), key)


def _sketch(name: str, entities: list[dict[str, Any]],
            plane: str = "Front Plane") -> dict[str, Any]:
    return {"name": name, "kind": "sketch", "plane": plane, "entities": entities}


def _circle(radius_mm: float, center: tuple[float, float] = (0.0, 0.0)) -> dict[str, Any]:
    return {"kind": "circle", "center": [center[0], center[1]], "radius_mm": radius_mm}


def _polygon(points: list[list[float]]) -> dict[str, Any]:
    return {"kind": "polyline", "closed": True, "points": points}


def _graph(part_type: str, parameters: dict[str, Any],
           features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": part_type,
            "parameters": parameters,
        },
        "features": features,
    }


# ------------------------------------------------------------------- 各零件

def _block(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    length = _param(parameters, "length_mm", 100.0)
    width = _param(parameters, "width_mm", 60.0)
    height = _param(parameters, "height_mm", 20.0)
    half_x, half_y = length / 2.0, width / 2.0
    return [
        {"name": "Part", "kind": "new_part", "title": "Block"},
        _sketch("BlockSketch", [_polygon([
            [-half_x, -half_y], [half_x, -half_y], [half_x, half_y], [-half_x, half_y],
        ])]),
        {"name": "BlockBoss", "kind": "boss_extrude", "sketch": "BlockSketch",
         "depth_mm": height},
    ]


def _cylinder(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    diameter = _param(parameters, "diameter_mm", 50.0)
    length = _param(parameters, "length_mm", 100.0)
    return [
        {"name": "Part", "kind": "new_part", "title": "Cylinder"},
        _sketch("CylinderSketch", [_circle(diameter / 2.0)]),
        {"name": "CylinderBoss", "kind": "boss_extrude", "sketch": "CylinderSketch",
         "depth_mm": length},
    ]


def _tube(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    outer = _param(parameters, "outer_diameter_mm", 50.0)
    inner = _param(parameters, "inner_diameter_mm", 40.0)
    length = _param(parameters, "length_mm", 100.0)
    if inner >= outer:
        raise ContractError("inner_diameter_mm must be smaller than outer_diameter_mm")
    # 同一草图里画内外两个圆，拉伸出来就是环形截面
    return [
        {"name": "Part", "kind": "new_part", "title": "Tube"},
        _sketch("TubeSketch", [_circle(outer / 2.0), _circle(inner / 2.0)]),
        {"name": "TubeBoss", "kind": "boss_extrude", "sketch": "TubeSketch",
         "depth_mm": length},
    ]


def _flange(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    outer = _param(parameters, "outer_diameter_mm", 120.0)
    bore = _param(parameters, "bore_diameter_mm", 40.0)
    thickness = _param(parameters, "thickness_mm", 12.0)
    bolt_circle = _param(parameters, "bolt_circle_diameter_mm", 90.0)
    hole = _param(parameters, "bolt_hole_diameter_mm", 10.0)

    count = parameters.get("bolt_count", 6)
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        raise ContractError("bolt_count must be an integer >= 2")
    if bore >= outer:
        raise ContractError("bore_diameter_mm must be smaller than outer_diameter_mm")
    if bolt_circle + hole >= outer:
        raise ContractError("bolt holes must stay inside outer_diameter_mm")

    hole_centers = [
        (
            bolt_circle / 2.0 * math.cos(2.0 * math.pi * index / count),
            bolt_circle / 2.0 * math.sin(2.0 * math.pi * index / count),
        )
        for index in range(count)
    ]
    return [
        {"name": "Part", "kind": "new_part", "title": "Flange"},
        _sketch("FlangeBlankSketch", [_circle(outer / 2.0)]),
        {"name": "FlangeBlank", "kind": "boss_extrude", "sketch": "FlangeBlankSketch",
         "depth_mm": thickness},
        _sketch("FlangeCutSketch",
                [_circle(bore / 2.0)] + [_circle(hole / 2.0, center)
                                         for center in hole_centers]),
        {"name": "FlangeCuts", "kind": "cut_extrude", "sketch": "FlangeCutSketch",
         "through_all": True},
    ]


def _stepped_shaft(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = parameters.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raw_steps = [
            {"diameter_mm": 40.0, "length_mm": 50.0},
            {"diameter_mm": 30.0, "length_mm": 40.0},
            {"diameter_mm": 20.0, "length_mm": 30.0},
        ]

    steps: list[tuple[float, float]] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ContractError(f"steps[{index}] must be an object")
        steps.append((
            require_positive(raw.get("diameter_mm"), f"steps[{index}].diameter_mm"),
            require_positive(raw.get("length_mm"), f"steps[{index}].length_mm"),
        ))

    # 半剖面：从轴心起，逐段走 (x, r) 台阶，最后回到轴心
    profile: list[list[float]] = [[0.0, 0.0]]
    cursor = 0.0
    for diameter, length in steps:
        radius = diameter / 2.0
        profile.append([cursor, radius])
        cursor += length
        profile.append([cursor, radius])
    profile.append([cursor, 0.0])

    return [
        {"name": "Part", "kind": "new_part", "title": "Stepped Shaft"},
        _sketch("ShaftProfileSketch", [
            # 构造线同时充当旋转轴（Line1 是草图里第一段）
            {"kind": "line", "start": [0.0, 0.0], "end": [cursor, 0.0],
             "construction": True},
            {"kind": "polyline", "closed": False, "points": profile},
        ]),
        {"name": "ShaftRevolve", "kind": "boss_revolve", "sketch": "ShaftProfileSketch",
         "axis_segment": "Line1", "angle_deg": 360.0},
    ]


_BUILDERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "block": _block,
    "cylinder": _cylinder,
    "tube": _tube,
    "flange": _flange,
    "stepped_shaft": _stepped_shaft,
}


# --------------------------------------------------------------------- 入口

def build_parametric_part_graph(part_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """把 ``part_type`` + 参数翻译成 Feature Graph IR。"""
    if not isinstance(parameters, dict):
        raise ContractError("parameters must be an object")

    normalized = str(part_type).strip().lower()
    builder = _BUILDERS.get(normalized)
    if builder is None:
        raise ContractError(f"part_type must be one of: {', '.join(PART_TYPES)}")

    return _graph(normalized, parameters, builder(parameters))
