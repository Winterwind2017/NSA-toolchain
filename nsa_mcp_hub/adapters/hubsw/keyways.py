"""标准键与键槽（GB/T 1096 平键 / GB/T 1095 键槽）。

工程上键槽不是"随便开个槽"：宽度和深度都按**轴径区间**查表，槽深还分
轴槽 ``t1`` 与毂槽 ``t2``。这个模块把表做成数据，并提供三种常用输出：

* :func:`key_for_shaft`    按轴径查出 ``b×h`` 与 ``t1/t2``
* :func:`shaft_keyway_outline` 轴上的圆头槽轮廓（可直接进 Feature Graph 草图）
* :func:`keyway_features`  生成"偏置基准面 → 槽草图 → 切除"三步特征

键长按 GB/T 1096 的长度系列取，超出系列时向上取整到最近的系列值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .contracts import ContractError, require_positive

#: 轴径上限 / 键宽 b / 键高 h / 轴槽深 t1 / 毂槽深 t2（GB/T 1096，mm）
KEY_TABLE: tuple[tuple[float, float, float, float, float], ...] = (
    (8.0, 2.0, 2.0, 1.2, 1.0),
    (10.0, 3.0, 3.0, 1.8, 1.4),
    (12.0, 4.0, 4.0, 2.5, 1.8),
    (17.0, 5.0, 5.0, 3.0, 2.3),
    (22.0, 6.0, 6.0, 3.5, 2.8),
    (30.0, 8.0, 7.0, 4.0, 3.3),
    (38.0, 10.0, 8.0, 5.0, 3.3),
    (44.0, 12.0, 8.0, 5.0, 3.3),
    (50.0, 14.0, 9.0, 5.5, 3.8),
    (58.0, 16.0, 10.0, 6.0, 4.3),
    (65.0, 18.0, 11.0, 7.0, 4.4),
    (75.0, 20.0, 12.0, 7.5, 4.9),
    (85.0, 22.0, 14.0, 9.0, 5.4),
    (95.0, 25.0, 14.0, 9.0, 5.4),
    (110.0, 28.0, 16.0, 10.0, 6.4),
    (130.0, 32.0, 18.0, 11.0, 7.4),
)

#: 键长系列（GB/T 1096 常用段）
LENGTH_SERIES = (10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40, 45, 50, 56, 63,
                 70, 80, 90, 100, 110, 125, 140, 160, 180, 200, 220, 250, 280, 320)


@dataclass(frozen=True)
class KeySpec:
    """一根轴上某个轴径对应的平键规格。"""

    shaft_diameter_mm: float
    width_mm: float
    height_mm: float
    shaft_depth_mm: float      # 轴槽深 t1
    hub_depth_mm: float        # 毂槽深 t2

    def to_dict(self) -> dict[str, Any]:
        return {
            "shaft_diameter_mm": self.shaft_diameter_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "shaft_depth_mm": self.shaft_depth_mm,
            "hub_depth_mm": self.hub_depth_mm,
            "standard": "GB/T 1096",
        }


def key_for_shaft(shaft_diameter_mm: float) -> KeySpec:
    """按轴径查平键规格；超出表格范围时拒绝（不做"猜一个"）。"""
    diameter = require_positive(shaft_diameter_mm, "shaft_diameter_mm")
    for limit, width, height, t1, t2 in KEY_TABLE:
        if diameter <= limit:
            return KeySpec(diameter, width, height, t1, t2)
    raise ContractError(
        f"shaft_diameter_mm={diameter} 超出 GB/T 1096 表格上限 "
        f"({KEY_TABLE[-1][0]} mm)，请改用花键或提供非标键槽尺寸")


def standard_length(length_mm: float) -> float:
    """把需要的键长向上取到标准系列值。"""
    required = require_positive(length_mm, "length_mm")
    for candidate in LENGTH_SERIES:
        if candidate >= required:
            return float(candidate)
    raise ContractError(f"length_mm={required} 超出标准长度系列上限")


def shaft_keyway_outline(
    start_mm: float,
    length_mm: float,
    width_mm: float,
    *,
    shaft_radius_mm: float,
    arc_segments: int = 8,
) -> list[list[float]]:
    """轴顶圆头键槽的闭合轮廓（坐标原点在轴心，槽底朝 +Y）。

    槽的两条直边落在 ``y = shaft_radius - 槽深`` 与 ``y = shaft_radius`` 上，
    两端各一个半圆（半径 = 键宽/2）。返回值可直接塞进 sketch 特征。
    """
    if arc_segments < 3:
        raise ContractError("arc_segments must be at least 3")
    radius = width_mm / 2.0
    left = start_mm + radius
    right = start_mm + length_mm - radius
    if right <= left:
        raise ContractError("length_mm must be longer than width_mm")

    points: list[list[float]] = []
    for index in range(arc_segments + 1):
        angle = math.pi / 2.0 + math.pi * index / arc_segments
        points.append([left + radius * math.cos(angle),
                       shaft_radius_mm - radius + radius * math.sin(angle)])
    for index in range(arc_segments + 1):
        angle = -math.pi / 2.0 + math.pi * index / arc_segments
        points.append([right + radius * math.cos(angle),
                       shaft_radius_mm - radius + radius * math.sin(angle)])
    return points


def keyway_features(
    name: str,
    *,
    plane: str,
    start_mm: float,
    length_mm: float,
    width_mm: float,
    shaft_radius_mm: float,
    depth_mm: float,
    reverse_direction: bool = False,
) -> list[dict[str, Any]]:
    """三步特征：偏置基准面（位于槽顶）→ 槽轮廓草图 → 向下切除。"""
    return [
        {
            "name": f"{name}Plane",
            "kind": "reference_plane_offset",
            "base_plane": "Front Plane",
            "offset_mm": shaft_radius_mm,
        },
        {
            "name": f"{name}Sketch",
            "kind": "sketch",
            "plane": f"{name}Plane",
            "entities": [{
                "kind": "polyline",
                "closed": True,
                "points": shaft_keyway_outline(
                    start_mm, length_mm, width_mm,
                    shaft_radius_mm=shaft_radius_mm),
            }],
        },
        {
            "name": f"{name}Cut",
            "kind": "cut_extrude",
            "sketch": f"{name}Sketch",
            "depth_mm": depth_mm,
            "reverse_direction": reverse_direction,
        },
    ]


def hub_groove_outline(
    shaft_radius_mm: float,
    key: KeySpec,
) -> list[list[float]]:
    """毂槽的矩形轮廓：宽度 = 键宽，深度 = t2（从孔径边起）。"""
    half = key.width_mm / 2.0
    inner = shaft_radius_mm
    outer = shaft_radius_mm + key.hub_depth_mm
    return [
        [-half, inner],
        [half, inner],
        [half, outer],
        [-half, outer],
    ]
