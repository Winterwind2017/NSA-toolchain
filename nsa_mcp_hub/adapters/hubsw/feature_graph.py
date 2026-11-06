"""Feature Graph IR：校验 + 编译成确定性的执行计划。

IR 的形态是一串**有序特征**（dict），每条描述一个 SolidWorks 原生特征；
编译产物是等长的步骤表，每步带 ``step`` / ``name`` / ``kind`` / ``operation``
和归一化后的参数，执行层按顺序落地，审计层可以离线复算。

三条硬规则：

* 版本必须是 ``"1.0"``，``features`` 非空；
* 第一个特征必须是 ``new_part``（其余特征都依附于它）；
* 引用只能指向**已经出现**的特征名——前向引用一律拒绝。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .contracts import ContractError, require_positive

#: 编译器认识的几何特征种类
FEATURE_KINDS = frozenset({
    "new_part",
    "sketch",
    "boss_extrude",
    "boss_revolve",
    "cut_extrude",
    "reference_plane_offset",
    "reference_axis",
    "circular_pattern",
    "fillet",
    "chamfer",
    # 早期版本遗留的"只编译不执行"特征，保留以兼容旧图
    "extrude",
})

#: 草图实体种类
SKETCH_KINDS = frozenset({"line", "circle", "arc", "spline", "polyline", "equation_spline"})

#: 选择器允许的朝向
ORIENTATIONS = frozenset({"any", "axial", "planar"})


# --------------------------------------------------------------- 基础归一化

def _coords(value: Any, name: str) -> list[float]:
    """把 (x, y) 或 (x, y, z) 归一化成 float 列表。"""
    if not isinstance(value, (list, tuple)) or len(value) not in (2, 3):
        raise ContractError(f"{name} must contain two or three coordinates")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} coordinates must be numbers") from exc


def _bool(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


# ------------------------------------------------------------- 草图实体归一化

def _line(entity: dict[str, Any], where: str) -> None:
    entity["start"] = _coords(entity.get("start"), f"{where}.start")
    entity["end"] = _coords(entity.get("end"), f"{where}.end")
    entity["construction"] = _bool(entity.get("construction"))


def _circle(entity: dict[str, Any], where: str) -> None:
    entity["center"] = _coords(entity.get("center", [0, 0]), f"{where}.center")
    entity["radius_mm"] = require_positive(entity.get("radius_mm"), f"{where}.radius_mm")


def _arc(entity: dict[str, Any], where: str) -> None:
    entity["center"] = _coords(entity.get("center"), f"{where}.center")
    entity["start"] = _coords(entity.get("start"), f"{where}.start")
    entity["end"] = _coords(entity.get("end"), f"{where}.end")
    direction = entity.get("direction", 1)
    if direction not in (-1, 1):
        raise ContractError(f"{where}.direction must be -1 or 1")
    entity["direction"] = direction


def _polyline(entity: dict[str, Any], where: str) -> None:
    points = entity.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ContractError(f"{where}.points must contain at least two points")
    entity["points"] = [_coords(point, f"{where}.points") for point in points]
    entity["closed"] = _bool(entity.get("closed"))


def _equation_spline(entity: dict[str, Any], where: str) -> None:
    for field in ("x_expression", "y_expression", "range_start", "range_end"):
        raw = entity.get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise ContractError(f"{where}.{field} must be a non-empty string")
        entity[field] = raw.strip()

    z_expression = entity.get("z_expression", "")
    if not isinstance(z_expression, str):
        raise ContractError(f"{where}.z_expression must be a string")
    entity["z_expression"] = z_expression.strip()
    entity["rotation_angle_deg"] = float(entity.get("rotation_angle_deg", 0.0))
    entity["x_offset_mm"] = float(entity.get("x_offset_mm", 0.0))
    entity["y_offset_mm"] = float(entity.get("y_offset_mm", 0.0))
    entity["lock_start"] = _bool(entity.get("lock_start"), True)
    entity["lock_end"] = _bool(entity.get("lock_end"), True)
    for anchor in ("start", "end"):
        if anchor in entity:
            entity[anchor] = _coords(entity[anchor], f"{where}.{anchor}")


_ENTITY_HANDLERS: dict[str, Callable[[dict[str, Any], str], None]] = {
    "line": _line,
    "circle": _circle,
    "arc": _arc,
    "spline": _polyline,
    "polyline": _polyline,
    "equation_spline": _equation_spline,
}


def _sketch_entities(value: Any, name: str) -> list[dict[str, Any]]:
    """校验并归一化草图实体数组（供 sketch 特征使用）。"""
    if not isinstance(value, list) or not value:
        raise ContractError(f"{name} must be a non-empty array")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        where = f"{name}[{index}]"
        if not isinstance(raw, dict):
            raise ContractError(f"{where} must be an object")
        kind = raw.get("kind")
        handler = _ENTITY_HANDLERS.get(kind) if isinstance(kind, str) else None
        if handler is None:
            raise ContractError(f"Unsupported sketch entity kind: {kind}")
        entity = deepcopy(raw)
        handler(entity, where)
        normalized.append(entity)
    return normalized


# ------------------------------------------------------------- 引用与选择器

def _reference(value: Any, seen: set[str], name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be a feature name")
    if value not in seen:
        raise ContractError(f"{name} references unknown or later feature: {value}")
    return value


def _selector(value: Any, name: str) -> dict[str, Any]:
    """面的选择器：朝向来过滤，几何量用来唯一确定面。"""
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    selector = deepcopy(value)
    orientation = selector.get("orientation", "any")
    if orientation not in ORIENTATIONS:
        raise ContractError(f"{name}.orientation must be any, axial, or planar")
    selector["orientation"] = orientation

    if "center_mm" in selector:
        selector["center_mm"] = _coords(selector["center_mm"], f"{name}.center_mm")
    for key in ("radius_mm", "radius_tolerance_mm", "tolerance_mm"):
        if key in selector:
            selector[key] = require_positive(selector[key], f"{name}.{key}")
    if "z_levels_mm" in selector:
        levels = selector["z_levels_mm"]
        if not isinstance(levels, list) or not levels:
            raise ContractError(f"{name}.z_levels_mm must be a non-empty array")
        selector["z_levels_mm"] = [float(level) for level in levels]
    if "expected_count" in selector:
        count = selector["expected_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ContractError(f"{name}.expected_count must be a positive integer")
    return selector


# ------------------------------------------------------------------ 单步构造

def _plane(feature: dict[str, Any], index: int, key: str = "plane") -> str:
    value = feature.get(key, "Front Plane")
    if not isinstance(value, str) or not value:
        raise ContractError(f"features[{index}].{key} must be a string")
    return value


def _step_new_part(feature: dict[str, Any], index: int, seen: set[str]) -> dict[str, Any]:
    if index != 0:
        raise ContractError("new_part can only be the first feature")
    return {"operation": "new_part", "title": str(feature.get("title",
                                                              feature.get("name")))}


def _step_sketch(feature: dict[str, Any], index: int, seen: set[str]) -> dict[str, Any]:
    return {
        "operation": "create_sketch",
        "plane": _plane(feature, index),
        "entities": _sketch_entities(feature.get("entities"), f"features[{index}].entities"),
    }


def _step_boss_extrude(feature: dict[str, Any], index: int,
                       seen: set[str]) -> dict[str, Any]:
    return {
        "operation": "boss_extrude",
        "sketch": _reference(feature.get("sketch"), seen, f"features[{index}].sketch"),
        "depth_mm": require_positive(feature.get("depth_mm"), f"features[{index}].depth_mm"),
        "merge": _bool(feature.get("merge"), True),
    }


def _step_boss_revolve(feature: dict[str, Any], index: int,
                       seen: set[str]) -> dict[str, Any]:
    """旋转：转轴既可以引用一条 reference_axis 特征，也可以指草图里的一段线。"""
    axis = feature.get("axis")
    axis_segment = feature.get("axis_segment")
    if (axis is None) == (axis_segment is None):
        raise ContractError(
            f"features[{index}] boss_revolve requires exactly one of axis or axis_segment")

    if axis is not None:
        normalized_axis = _reference(axis, seen, f"features[{index}].axis")
        normalized_segment = None
        strategy = "reference_axis"
    else:
        if not isinstance(axis_segment, str) or not axis_segment.strip():
            raise ContractError(f"features[{index}].axis_segment must be a non-empty string")
        normalized_axis = None
        normalized_segment = axis_segment.strip()
        strategy = "sketch_segment"

    return {
        "operation": "boss_revolve",
        "sketch": _reference(feature.get("sketch"), seen, f"features[{index}].sketch"),
        "axis": normalized_axis,
        "axis_segment": normalized_segment,
        "axis_strategy": strategy,
        "angle_deg": require_positive(feature.get("angle_deg", 360.0),
                                      f"features[{index}].angle_deg"),
        "merge": _bool(feature.get("merge"), True),
    }


def _step_cut_extrude(feature: dict[str, Any], index: int,
                      seen: set[str]) -> dict[str, Any]:
    through_all = _bool(feature.get("through_all"))
    depth = feature.get("depth_mm")
    if not through_all:
        depth = require_positive(depth, f"features[{index}].depth_mm")
    return {
        "operation": "cut_extrude",
        "sketch": _reference(feature.get("sketch"), seen, f"features[{index}].sketch"),
        "through_all": through_all,
        "depth_mm": float(depth) if depth is not None else None,
        "reverse_direction": _bool(feature.get("reverse_direction")),
    }


def _step_plane_offset(feature: dict[str, Any], index: int,
                       seen: set[str]) -> dict[str, Any]:
    offset = float(feature.get("offset_mm", 0.0))
    if offset == 0.0:
        raise ContractError(f"features[{index}].offset_mm must be non-zero")
    return {
        "operation": "reference_plane_offset",
        "base_plane": _plane(feature, index, "base_plane"),
        "offset_mm": offset,
    }


def _step_reference_axis(feature: dict[str, Any], index: int,
                         seen: set[str]) -> dict[str, Any]:
    planes = feature.get("planes")
    if (not isinstance(planes, list) or len(planes) != 2
            or not all(isinstance(item, str) for item in planes)):
        raise ContractError(f"features[{index}].planes must contain exactly two plane names")
    return {"operation": "reference_axis", "planes": list(planes)}


def _step_circular_pattern(feature: dict[str, Any], index: int,
                           seen: set[str]) -> dict[str, Any]:
    count = feature.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        raise ContractError(f"features[{index}].count must be an integer >= 2")
    return {
        "operation": "circular_pattern",
        "feature": _reference(feature.get("feature"), seen, f"features[{index}].feature"),
        "axis": _reference(feature.get("axis"), seen, f"features[{index}].axis"),
        "count": count,
        "total_angle_deg": require_positive(feature.get("total_angle_deg", 360.0),
                                            f"features[{index}].total_angle_deg"),
        "geometry_pattern": _bool(feature.get("geometry_pattern"), True),
    }


def _step_fillet(feature: dict[str, Any], index: int, seen: set[str]) -> dict[str, Any]:
    return {
        "operation": "fillet",
        "radius_mm": require_positive(feature.get("radius_mm"), f"features[{index}].radius_mm"),
        "selector": _selector(feature.get("selector"), f"features[{index}].selector"),
    }


def _step_chamfer(feature: dict[str, Any], index: int, seen: set[str]) -> dict[str, Any]:
    return {
        "operation": "chamfer",
        "distance_mm": require_positive(feature.get("distance_mm"),
                                        f"features[{index}].distance_mm"),
        "angle_deg": require_positive(feature.get("angle_deg", 45.0),
                                      f"features[{index}].angle_deg"),
        "selector": _selector(feature.get("selector"), f"features[{index}].selector"),
    }


def _step_legacy_extrude(feature: dict[str, Any], index: int,
                         seen: set[str]) -> dict[str, Any]:
    """早期版本的 extrude：只编译成一步占位，执行层不落地。"""
    depth = require_positive(feature.get("depth_mm"), f"features[{index}].depth_mm")
    profile = feature.get("profile")
    if profile not in ("circle", "rectangle"):
        raise ContractError("extrude.profile must be circle or rectangle")
    return {
        "operation": "create_sketch_and_extrude",
        "profile": profile,
        "depth_mm": depth,
        "status": "compile_only_legacy",
    }


_STEP_BUILDERS: dict[str, Callable[[dict[str, Any], int, set[str]], dict[str, Any]]] = {
    "new_part": _step_new_part,
    "sketch": _step_sketch,
    "boss_extrude": _step_boss_extrude,
    "boss_revolve": _step_boss_revolve,
    "cut_extrude": _step_cut_extrude,
    "reference_plane_offset": _step_plane_offset,
    "reference_axis": _step_reference_axis,
    "circular_pattern": _step_circular_pattern,
    "fillet": _step_fillet,
    "chamfer": _step_chamfer,
    "extrude": _step_legacy_extrude,
}


# --------------------------------------------------------------------- 入口

def compile_feature_graph(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """校验 IR 并编译成步骤表；任何不合契约的地方都抛 :class:`ContractError`。"""
    if not isinstance(graph, dict):
        raise ContractError("feature_graph must be an object")
    if graph.get("version") != "1.0":
        raise ContractError("feature_graph.version must be '1.0'")

    features = graph.get("features")
    if not isinstance(features, list) or not features:
        raise ContractError("feature_graph.features must be a non-empty array")

    plan: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ContractError(f"features[{index}] must be an object")

        name = feature.get("name")
        kind = feature.get("kind")
        if not isinstance(name, str) or not name or name in seen:
            raise ContractError(f"features[{index}].name must be unique")
        if kind not in FEATURE_KINDS:
            raise ContractError(f"Unsupported feature kind: {kind}")
        if index == 0 and kind != "new_part":
            raise ContractError("The first feature must be new_part")

        step: dict[str, Any] = {"step": index + 1, "name": name, "kind": kind}
        step.update(_STEP_BUILDERS[kind](feature, index, seen))
        plan.append(step)
        seen.add(name)

    return plan
