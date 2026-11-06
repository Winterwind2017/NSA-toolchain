"""斜齿圆柱齿轮：参数换算 + 分层（lamina）Feature Graph。

斜齿轮的齿沿轴向**扭转**，真螺旋面要么扫掠要么放样——这两条在当前的
Feature Graph IR 里都没有（IR 只有拉伸/旋转/切除/阵列）。所以这里做的是
**工程上可用的分层近似**：把齿宽切成 N 片，每片用同一个渐开线齿形、绕轴
转过一个固定增量再拉伸。片数越多越接近真实螺旋，片数写在 metadata 里，
不会假装是螺旋面。

参数换算按 ISO 斜齿轮基本关系：

* 端面模数 ``mt = mn / cosβ``
* 端面压力角 ``αt = atan(tan αn / cos β)``
* 分度圆 ``d = mt·z``，导程 ``L = π·d / tanβ``
* 整圈扭转角 ``θ = b·tanβ / r``
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import ContractError, require_positive
from .involute_gear import tooth_outline_points

#: 单片齿形默认采样数（齿宽方向切片数由调用方给）
DEFAULT_SLICES = 8


@dataclass
class HelicalGearSpec:
    module_normal_mm: float
    module_transverse_mm: float
    tooth_count: int
    pressure_angle_normal_deg: float
    pressure_angle_transverse_deg: float
    helix_angle_deg: float
    thickness_mm: float
    bore_diameter_mm: float
    slices: int
    pitch_radius_mm: float
    base_radius_mm: float
    root_radius_mm: float
    outer_radius_mm: float
    lead_mm: float
    total_twist_rad: float
    slice_thickness_mm: float
    twist_per_slice_rad: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_helical_gear_spec(
    *,
    module_normal_mm: float,
    tooth_count: int,
    pressure_angle_normal_deg: float,
    helix_angle_deg: float,
    thickness_mm: float,
    bore_diameter_mm: float,
    slices: int = DEFAULT_SLICES,
) -> HelicalGearSpec:
    """校验参数并换算端面量、导程与扭转角。"""
    mn = require_positive(module_normal_mm, "module_normal_mm")
    thickness = require_positive(thickness_mm, "thickness_mm")
    bore = require_positive(bore_diameter_mm, "bore_diameter_mm")
    alpha_n = require_positive(pressure_angle_normal_deg, "pressure_angle_normal_deg")
    beta = require_positive(helix_angle_deg, "helix_angle_deg")

    if not isinstance(tooth_count, int) or isinstance(tooth_count, bool):
        raise ContractError("tooth_count must be an integer")
    if not 8 <= tooth_count <= 160:
        raise ContractError("tooth_count must be an integer from 8 to 160")
    if not 14.5 <= alpha_n <= 30.0:
        raise ContractError("pressure_angle_normal_deg must be from 14.5 to 30")
    if not 5.0 <= beta <= 45.0:
        raise ContractError("helix_angle_deg must be from 5 to 45 degrees")
    if not isinstance(slices, int) or isinstance(slices, bool) or not 2 <= slices <= 24:
        raise ContractError("slices must be an integer from 2 to 24")

    beta_rad = math.radians(beta)
    mt = mn / math.cos(beta_rad)
    alpha_t = math.atan(math.tan(math.radians(alpha_n)) / math.cos(beta_rad))

    pitch = mt * tooth_count / 2.0
    base = pitch * math.cos(alpha_t)
    root = pitch - 1.25 * mn
    outer = pitch + mn
    lead = math.pi * 2.0 * pitch / math.tan(beta_rad)
    total_twist = thickness * math.tan(beta_rad) / pitch

    if root <= 0.0:
        raise ContractError("module/tooth_count produces a non-positive root radius")
    if bore / 2.0 >= root - 0.5 * mn:
        raise ContractError("bore_diameter_mm leaves insufficient material at the tooth root")

    slice_thickness = thickness / slices
    if slice_thickness < 0.2:
        raise ContractError("切片过薄（<0.2 mm）：请减少 slices 或加大齿宽")

    return HelicalGearSpec(
        module_normal_mm=mn,
        module_transverse_mm=mt,
        tooth_count=tooth_count,
        pressure_angle_normal_deg=alpha_n,
        pressure_angle_transverse_deg=math.degrees(alpha_t),
        helix_angle_deg=beta,
        thickness_mm=thickness,
        bore_diameter_mm=bore,
        slices=slices,
        pitch_radius_mm=pitch,
        base_radius_mm=base,
        root_radius_mm=root,
        outer_radius_mm=outer,
        lead_mm=lead,
        total_twist_rad=total_twist,
        slice_thickness_mm=slice_thickness,
        twist_per_slice_rad=total_twist / slices,
    )


def _slice_outline(spec: HelicalGearSpec, slice_rotation_rad: float,
                   samples_per_flank: int = 12) -> list[list[float]]:
    """一整片齿轮的闭合轮廓：按齿拼单齿轮廓，齿与齿之间用齿根弦连接。"""
    pitch_angle = 2.0 * math.pi / spec.tooth_count
    outline: list[list[float]] = []
    for index in range(spec.tooth_count):
        outline.extend(tooth_outline_points(
            pitch_radius_mm=spec.pitch_radius_mm,
            base_radius_mm=spec.base_radius_mm,
            root_radius_mm=spec.root_radius_mm,
            outer_radius_mm=spec.outer_radius_mm,
            tooth_count=spec.tooth_count,
            rotation_rad=index * pitch_angle + slice_rotation_rad,
            samples_per_flank=samples_per_flank,
            samples_across_tip=4,
        ))
    return outline


def build_helical_gear_graph(spec: HelicalGearSpec) -> dict[str, Any]:
    """分层建斜齿轮：每片"草图 + 拉伸"，最后钻轴孔。"""
    features: list[dict[str, Any]] = [
        {"name": "HelicalGear", "kind": "new_part", "title": "Helical Gear (lamina)"},
    ]
    for index in range(spec.slices):
        rotation = index * spec.twist_per_slice_rad
        plane = "Front Plane"
        if index > 0:
            # 每片必须落在自己的偏置面上，否则所有切片都堆在 z=0，只算一片的料
            plane = f"Slice{index + 1}Plane"
            features.append({
                "name": plane,
                "kind": "reference_plane_offset",
                "base_plane": "Front Plane",
                "offset_mm": index * spec.slice_thickness_mm,
            })
        features += [
            {
                "name": f"Slice{index + 1}Sketch",
                "kind": "sketch",
                "plane": plane,
                "entities": [{"kind": "polyline", "closed": True,
                              "points": _slice_outline(spec, rotation)}],
            },
            {
                "name": f"Slice{index + 1}Boss",
                "kind": "boss_extrude",
                "sketch": f"Slice{index + 1}Sketch",
                "depth_mm": spec.slice_thickness_mm,
                "merge": True,
            },
        ]
    features += [
        {
            "name": "BoreSketch",
            "kind": "sketch",
            "plane": "Front Plane",
            "entities": [{"kind": "circle", "center": [0.0, 0.0],
                          "radius_mm": spec.bore_diameter_mm / 2.0}],
        },
        {"name": "BoreCut", "kind": "cut_extrude", "sketch": "BoreSketch",
         "through_all": True},
    ]

    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": "helical_spur_gear_lamina",
            "gear_spec": spec.to_dict(),
            "approximation": "lamina stack: %d slices, twist %.4f rad/slice"
                             % (spec.slices, spec.twist_per_slice_rad),
            "features_per_slice": 3,  # 偏置面 + 草图 + 拉伸
        },
        "features": features,
    }
