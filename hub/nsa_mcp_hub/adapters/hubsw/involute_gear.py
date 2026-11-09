"""渐开线直齿轮：几何计算 + Feature Graph 生成。

几何按 ISO 基本齿条推：

* 分度圆 ``r = m·z/2``，基圆 ``rb = r·cosα``
* 齿顶 ``ra = r + m``，齿根 ``rf = r − 1.25m``（标准全齿高）
* 分度圆上半齿角 ``π/(2z)``，齿厚 ``πm/2``

齿廓用"滚动角"参数化：在基圆坐标系里取
``x = rb(cos t + t sin t)``、``y = −rb(sin t − t cos t)``，再整体旋转
``π/(2z) + inv(α)``，得到上侧齿面；镜像即下侧。采样成一条闭合折线，
在 SolidWorks 里作为原生 polyline 拉伸，再把单齿环形阵列 z 次。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import ContractError, require_positive

#: 齿数 / 压力角的可接受范围（超出即拒绝，避免做出"看起来像齿轮"的怪物）
MIN_TEETH, MAX_TEETH = 8, 160
MIN_PRESSURE_ANGLE, MAX_PRESSURE_ANGLE = 14.5, 30.0


@dataclass
class InvoluteGearSpec:
    """一个直齿轮的完整几何定义（构造后不再变）。"""

    module_mm: float
    tooth_count: int
    pressure_angle_deg: float
    thickness_mm: float
    bore_diameter_mm: float
    root_fillet_mm: float
    tip_chamfer_mm: float
    pitch_radius_mm: float
    base_radius_mm: float
    root_radius_mm: float
    outer_radius_mm: float
    #: 变位系数 x（正变位齿顶外移、齿厚增加）；0 即标准齿轮
    profile_shift_x: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def involute_angle(radius: float, base_radius: float) -> float:
    """渐开线展开角 ``inv(α) = tan α − α``（用半径比反算）。"""
    if radius < base_radius:
        raise ContractError("An involute is undefined below its base circle")
    alpha = math.acos(base_radius / radius)
    return math.tan(alpha) - alpha


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.cos(angle), radius * math.sin(angle)]


def validate_gear_spec(
    *,
    module_mm: float,
    tooth_count: int,
    pressure_angle_deg: float,
    thickness_mm: float,
    bore_diameter_mm: float,
    root_fillet_mm: float,
    tip_chamfer_mm: float,
    profile_shift_x: float = 0.0,
) -> InvoluteGearSpec:
    """校验参数并算出四个特征圆半径；不合规就抛 ContractError。"""
    module = require_positive(module_mm, "module_mm")
    angle_deg = require_positive(pressure_angle_deg, "pressure_angle_deg")
    thickness = require_positive(thickness_mm, "thickness_mm")
    bore = require_positive(bore_diameter_mm, "bore_diameter_mm")
    fillet = require_positive(root_fillet_mm, "root_fillet_mm")
    chamfer = require_positive(tip_chamfer_mm, "tip_chamfer_mm")

    if not isinstance(tooth_count, int) or isinstance(tooth_count, bool):
        raise ContractError("tooth_count must be an integer")
    if not MIN_TEETH <= tooth_count <= MAX_TEETH:
        raise ContractError(
            f"tooth_count must be an integer from {MIN_TEETH} to {MAX_TEETH}")
    if not MIN_PRESSURE_ANGLE <= angle_deg <= MAX_PRESSURE_ANGLE:
        raise ContractError(
            f"pressure_angle_deg must be from {MIN_PRESSURE_ANGLE} to "
            f"{MAX_PRESSURE_ANGLE} degrees")

    try:
        shift = float(profile_shift_x)
    except (TypeError, ValueError) as exc:
        raise ContractError("profile_shift_x must be a number") from exc
    if not -0.8 <= shift <= 1.0:
        raise ContractError("profile_shift_x must be within -0.8 .. 1.0")

    pitch = module * tooth_count / 2.0
    base = pitch * math.cos(math.radians(angle_deg))
    # 变位：齿顶外移 x·m，齿根内收 (1.25 - x)·m
    root = pitch - (1.25 - shift) * module
    outer = pitch + (1.0 + shift) * module

    if root <= 0.0:
        raise ContractError("module/tooth_count produces a non-positive root radius")
    if bore / 2.0 >= root - fillet:
        raise ContractError("bore_diameter_mm leaves insufficient material at the tooth root")
    if fillet >= module:
        raise ContractError("root_fillet_mm must be smaller than module_mm")
    if chamfer >= module / 2.0:
        raise ContractError("tip_chamfer_mm must be smaller than half the module")

    return InvoluteGearSpec(
        module_mm=module,
        tooth_count=tooth_count,
        pressure_angle_deg=angle_deg,
        thickness_mm=thickness,
        bore_diameter_mm=bore,
        root_fillet_mm=fillet,
        tip_chamfer_mm=chamfer,
        pitch_radius_mm=pitch,
        base_radius_mm=base,
        root_radius_mm=root,
        outer_radius_mm=outer,
        profile_shift_x=shift,
    )


def tooth_outline_points(
    *,
    pitch_radius_mm: float,
    base_radius_mm: float,
    root_radius_mm: float,
    outer_radius_mm: float,
    tooth_count: int,
    rotation_rad: float = 0.0,
    samples_per_flank: int = 16,
    samples_across_tip: int = 5,
    profile_shift_x: float = 0.0,
    pressure_angle_deg: float = 20.0,
) -> list[list[float]]:
    """一个齿的闭合轮廓（齿根 → 一侧齿面 → 齿顶圆弧 → 另一侧齿面 → 齿根）。

    斜齿轮、内齿轮、外齿轮共用这套点，齿形不会各写一份而慢慢漂移。
    """
    if samples_per_flank < 6:
        raise ContractError("samples_per_flank must be at least 6")
    if samples_across_tip < 2:
        raise ContractError("samples_across_tip must be at least 2")

    half_tooth = (math.pi / (2.0 * tooth_count)
                  + 2.0 * profile_shift_x
                  * math.tan(math.radians(pressure_angle_deg)) / tooth_count)
    base_half = half_tooth + involute_angle(pitch_radius_mm, base_radius_mm)

    # 渐开线只在基圆以外存在；齿根圆比基圆大时（z 大，约 z>=42），齿面从齿根圆起算，
    # 否则轮廓会先掉到基圆再回来，形成一个小钩子（自交）。
    start_radius = max(base_radius_mm, root_radius_mm)
    roll_end = math.sqrt((outer_radius_mm / base_radius_mm) ** 2 - 1.0)
    roll_start = math.sqrt((start_radius / base_radius_mm) ** 2 - 1.0)

    flank: list[list[float]] = []
    for index in range(samples_per_flank):
        t = roll_start + (roll_end - roll_start) * index / (samples_per_flank - 1)
        x = base_radius_mm * (math.cos(t) + t * math.sin(t))
        y = -base_radius_mm * (math.sin(t) - t * math.cos(t))
        cos_a, sin_a = math.cos(base_half), math.sin(base_half)
        flank.append([x * cos_a - y * sin_a, x * sin_a + y * cos_a])

    mirrored = [[point[0], -point[1]] for point in flank]
    tip_half = math.atan2(flank[-1][1], flank[-1][0])
    tip_arc = [
        _polar(outer_radius_mm,
               -tip_half + 2.0 * tip_half * index / (samples_across_tip - 1))
        for index in range(samples_across_tip)
    ]

    local: list[list[float]] = [
        _polar(root_radius_mm, -base_half),
        *mirrored,
        *tip_arc[1:-1],
        *reversed(flank),
        _polar(root_radius_mm, base_half),
    ]
    cos_r, sin_r = math.cos(rotation_rad), math.sin(rotation_rad)
    return [[x * cos_r - y * sin_r, x * sin_r + y * cos_r] for x, y in local]


def sampled_involute_tooth_points(
    spec: InvoluteGearSpec,
    *,
    center_mm: tuple[float, float] = (0.0, 0.0),
    rotation_rad: float = 0.0,
    samples_per_flank: int = 16,
    samples_across_tip: int = 5,
) -> list[list[float]]:
    """单齿闭合折线；坐标平移到 ``center_mm``。"""
    local = tooth_outline_points(
        pitch_radius_mm=spec.pitch_radius_mm,
        base_radius_mm=spec.base_radius_mm,
        root_radius_mm=spec.root_radius_mm,
        outer_radius_mm=spec.outer_radius_mm,
        tooth_count=spec.tooth_count,
        rotation_rad=rotation_rad,
        samples_per_flank=samples_per_flank,
        samples_across_tip=samples_across_tip,
        profile_shift_x=getattr(spec, "profile_shift_x", 0.0),
        pressure_angle_deg=spec.pressure_angle_deg,
    )
    cx, cy = center_mm
    return [[cx + point[0], cy + point[1]] for point in local]


def sampled_involute_gear_entities(
    spec: InvoluteGearSpec,
    *,
    center_mm: tuple[float, float] = (0.0, 0.0),
    samples_per_flank: int = 16,
) -> list[dict[str, Any]]:
    """每齿一条闭合 polyline（供"整圈画出来"的场合使用）。"""
    pitch_angle = 2.0 * math.pi / spec.tooth_count
    return [
        {
            "kind": "polyline",
            "closed": True,
            "points": sampled_involute_tooth_points(
                spec,
                center_mm=center_mm,
                rotation_rad=index * pitch_angle,
                samples_per_flank=samples_per_flank,
            ),
        }
        for index in range(spec.tooth_count)
    ]


def involute_tooth_entities(spec: InvoluteGearSpec) -> list[dict[str, Any]]:
    """等价的"方程样条"表示：两侧齿面各一条方程样条，根部与顶弧用直线收口。

    只给支持稳定方程样条的宿主用；默认走采样折线。
    """
    half_tooth = math.pi / (2.0 * spec.tooth_count)
    base_half_deg = math.degrees(
        half_tooth + involute_angle(spec.pitch_radius_mm, spec.base_radius_mm))
    roll_end = math.sqrt((spec.outer_radius_mm / spec.base_radius_mm) ** 2 - 1.0)
    base = spec.base_radius_mm

    upper = {
        "kind": "equation_spline",
        "x_expression": f"{base}*(cos(t)+t*sin(t))",
        "y_expression": f"-{base}*(sin(t)-t*cos(t))",
        "range_start": "0",
        "range_end": f"{roll_end}",
        "rotation_angle_deg": base_half_deg,
    }
    lower = {
        "kind": "equation_spline",
        "x_expression": f"{base}*(cos(t)+t*sin(t))",
        "y_expression": f"{base}*(sin(t)-t*cos(t))",
        "range_start": "0",
        "range_end": f"{roll_end}",
        "rotation_angle_deg": -base_half_deg,
    }
    return [
        lower,
        {"kind": "line",
         "start": _polar(spec.outer_radius_mm, -math.radians(base_half_deg)),
         "end": _polar(spec.outer_radius_mm, math.radians(base_half_deg))},
        upper,
        {"kind": "line",
         "start": _polar(spec.root_radius_mm, math.radians(base_half_deg)),
         "end": _polar(spec.root_radius_mm, -math.radians(base_half_deg))},
    ]


def build_involute_gear_graph(
    spec: InvoluteGearSpec,
    tooth_representation: str = "sampled_polyline",
    include_finishing: bool = True,
) -> dict[str, Any]:
    """生成"齿坯 + 单齿 + 环形阵列 + 轴孔"的原生特征图。

    ``include_finishing`` 打开时追加齿根圆角与齿顶倒角（SW 2025 上该路径
    依赖 FeatureFillet，实测不可用，故工具层默认关掉）。
    """
    if tooth_representation not in ("sampled_polyline", "equation_spline"):
        raise ContractError("tooth_representation must be sampled_polyline or equation_spline")

    tooth_entities = (
        [{
            "kind": "polyline",
            "closed": True,
            "points": sampled_involute_tooth_points(spec, samples_per_flank=16),
        }]
        if tooth_representation == "sampled_polyline"
        else involute_tooth_entities(spec)
    )

    features: list[dict[str, Any]] = [
        {"name": "Part", "kind": "new_part", "title": "Involute Spur Gear"},
        {
            "name": "GearBlankSketch",
            "kind": "sketch",
            "plane": "Front Plane",
            "entities": [{"kind": "circle", "center": [0.0, 0.0],
                          "radius_mm": spec.root_radius_mm}],
        },
        {"name": "GearBlank", "kind": "boss_extrude", "sketch": "GearBlankSketch",
         "depth_mm": spec.thickness_mm},
        {"name": "GearAxis", "kind": "reference_axis",
         "planes": ["Top Plane", "Right Plane"]},
        {"name": "InvoluteToothSketch", "kind": "sketch", "plane": "Front Plane",
         "entities": tooth_entities},
        {"name": "ToothBoss", "kind": "boss_extrude", "sketch": "InvoluteToothSketch",
         "depth_mm": spec.thickness_mm, "merge": True},
        {"name": "ToothCircularPattern", "kind": "circular_pattern",
         "feature": "ToothBoss", "axis": "GearAxis", "count": spec.tooth_count,
         "total_angle_deg": 360.0, "geometry_pattern": True},
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

    if include_finishing:
        tolerance = max(0.08, spec.module_mm * 0.08)
        features += [
            {
                "name": "RootFillet",
                "kind": "fillet",
                "radius_mm": spec.root_fillet_mm,
                "selector": {
                    "orientation": "axial",
                    "radius_mm": spec.root_radius_mm,
                    "radius_tolerance_mm": tolerance,
                    "expected_count": spec.tooth_count * 2,
                },
            },
            {
                "name": "TipChamfer",
                "kind": "chamfer",
                "distance_mm": spec.tip_chamfer_mm,
                "angle_deg": 45.0,
                "selector": {
                    "orientation": "planar",
                    "radius_mm": spec.outer_radius_mm,
                    "radius_tolerance_mm": tolerance,
                    "expected_count": spec.tooth_count * 2,
                },
            },
        ]

    return {
        "version": "1.0",
        "metadata": {
            "generator": "nsa-mcp-hub",
            "part_type": "involute_spur_gear",
            "gear_spec": spec.to_dict(),
            "bore_fit": "H7",
            "tooth_representation": tooth_representation,
            "finishing_features_included": include_finishing,
        },
        "features": features,
    }
