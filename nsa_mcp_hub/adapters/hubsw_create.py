"""SW「一步到位」封装：一次调用 = 生成 Feature Graph + 执行到 SolidWorks。

上游 `create_*` 是一步（直接建模型），hub 原来只有两半：
`sw_*_plan`（出图）和 `sw_execute_feature_graph`（执行）。
这里把它们缝成一条调用，参数与执行结果都保持可比：

* `execute=false` → 只出图（不需要开 SolidWorks，判据是图的结构）；
* `execute=true`（默认）→ 出图后立刻执行，判据沿用执行器那一套
  （plan_steps / steps_ok / body_volume_mm3 …）。

安全默认：执行器永远**新建文档**，不碰用户已打开的文件（上游同样语义）。
"""

from __future__ import annotations

import math
from typing import Any

from ..tools import ToolSpec, normalize
from .hubsw import gearbox as gb
from .hubsw import involute_gear as ig
from .hubsw import output_shaft as os_
from .hubsw import part_generators as pg
from .hubsw import primitives as pr
from .hubsw_exec import execute_feature_graph
from .hubsw_feat import _check

KIT_KEY = "sw"

_TYPE_NUM = {"type": "number"}
_TYPE_BOOL = {"type": "boolean"}
_TYPE_STR = {"type": "string"}
_TYPE_OBJ = {"type": "object"}
HEX40 = r"^[0-9a-fA-F]{40}$"


def _steps(graph: dict) -> int:
    if not isinstance(graph, dict):
        return 0
    for key in ("features", "steps", "plan", "nodes"):
        value = graph.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _names(graph: dict) -> list[str]:
    if not isinstance(graph, dict):
        return []
    for key in ("features", "steps", "plan", "nodes"):
        value = graph.get(key)
        if isinstance(value, list):
            return [str(item.get("name")) for item in value if isinstance(item, dict)]
    return []


def _compose(name: str, graph: dict, args: dict) -> dict:
    """图已生成；按 execute 决定是收工还是交给执行器。"""
    steps = _steps(graph)
    reads: dict[str, Any] = {
        "graph_steps": steps,
        "feature_names": _names(graph),
        "executed": False,
    }
    checks = [_check("graph_built", steps, ">0", steps > 0),
              _check("feature_names", len(_names(graph)), ">0", bool(_names(graph)))]
    if args.get("include_graph"):
        reads["feature_graph"] = graph

    if not steps:
        return normalize(KIT_KEY, name, ok=False, reads=reads,
                         errors=["生成的 Feature Graph 没有特征"])

    errors: list[str] = []
    if args.get("execute", True) is not False:
        exec_args: dict[str, Any] = {"feature_graph": graph}
        if args.get("expected_volume_mm3") is not None:
            exec_args["expected_volume_mm3"] = float(args["expected_volume_mm3"])
        if args.get("save_path"):
            exec_args["save_path"] = str(args["save_path"])
        result = execute_feature_graph(exec_args)
        reads["executed"] = True
        reads["execute"] = {
            "ok": result.get("ok"),
            "title": (result.get("reads") or {}).get("title"),
            "plan_steps": (result.get("reads") or {}).get("plan_steps"),
            "steps_ok": (result.get("reads") or {}).get("steps_ok"),
            "body_volume_mm3": (result.get("reads") or {}).get("body_volume_mm3"),
            "features_tail": (result.get("reads") or {}).get("features_tail"),
        }
        checks.append(_check("executed", result.get("ok"), True, bool(result.get("ok"))))
        for item in result.get("checks") or []:
            if isinstance(item, dict):
                checks.append(item)
        errors.extend(result.get("errors") or [])

    ok = all(c.get("ok") for c in checks) and not errors
    return normalize(KIT_KEY, name, ok=ok, reads=reads, errors=errors, checks=checks)


# --------------------------------------------------------------- 各 create_*

def _gear_spec(module_mm: float, tooth_count: int, pressure_angle_deg: float,
               thickness_mm: float, bore_diameter_mm: float,
               root_fillet_mm: float | None, tip_chamfer_mm: float | None):
    module = float(module_mm)
    teeth = int(tooth_count)
    if module <= 0:
        raise ValueError("module_mm must be positive")
    if teeth < 6:
        raise ValueError("tooth_count must be >= 6")
    angle = float(pressure_angle_deg)
    pitch_radius = module * teeth / 2.0
    return ig.InvoluteGearSpec(
        module_mm=module,
        tooth_count=teeth,
        pressure_angle_deg=angle,
        thickness_mm=float(thickness_mm),
        bore_diameter_mm=float(bore_diameter_mm),
        root_fillet_mm=float(root_fillet_mm if root_fillet_mm is not None else 0.38 * module),
        tip_chamfer_mm=float(tip_chamfer_mm if tip_chamfer_mm is not None else 0.1 * module),
        pitch_radius_mm=pitch_radius,
        base_radius_mm=pitch_radius * math.cos(math.radians(angle)),
        root_radius_mm=pitch_radius - 1.25 * module,
        outer_radius_mm=pitch_radius + module,
    )


def create_involute_gear(args: dict) -> dict:
    try:
        spec = _gear_spec(args.get("module_mm", 2.0), args.get("tooth_count", 20),
                          args.get("pressure_angle_deg", 20.0),
                          args.get("thickness_mm", 10.0),
                          args.get("bore_diameter_mm", 10.0),
                          args.get("root_fillet_mm"), args.get("tip_chamfer_mm"))
        graph = ig.build_involute_gear_graph(spec)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_involute_gear", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    reads = {"spec": {k: getattr(spec, k) for k in
                      ("module_mm", "tooth_count", "pressure_angle_deg",
                       "thickness_mm", "bore_diameter_mm", "pitch_radius_mm",
                       "outer_radius_mm", "root_radius_mm")}}
    payload = _compose("create_involute_gear", graph, args)
    payload["reads"].update(reads)
    return payload


def create_sphere(args: dict) -> dict:
    try:
        diameter = float(args.get("diameter_mm", 50.0))
        graph = pr.build_sphere_graph(diameter)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_sphere", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    payload = _compose("create_sphere", graph, args)
    radius = diameter / 2.0
    payload["reads"].update({"diameter_mm": diameter,
                             "analytic_volume_mm3": round(4.0 / 3.0 * math.pi * radius ** 3, 3)})
    return payload


def create_parametric_part(args: dict) -> dict:
    try:
        graph = pg.build_parametric_part_graph(str(args.get("part_type", "block")),
                                              args.get("parameters") or {})
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_parametric_part", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    return _compose("create_parametric_part", graph, args)


def create_two_stage_reducer(args: dict) -> dict:
    try:
        kwargs = {k: args[k] for k in
                  ("module_mm", "pressure_angle_deg", "gear_thickness_mm", "axial_gap_mm",
                   "radial_clearance_mm", "shaft_extension_mm") if k in args}
        for key in ("stage1_teeth", "stage2_teeth", "bore_diameters_mm"):
            if key in args and args[key] is not None:
                kwargs[key] = tuple(args[key])
        graph = gb.build_two_stage_reducer_graph(**kwargs)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_two_stage_reducer", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    payload = _compose("create_two_stage_reducer", graph, args)
    stage1 = args.get("stage1_teeth") or (20, 40)
    stage2 = args.get("stage2_teeth") or (20, 60)
    module = float(args.get("module_mm", 2.0))
    payload["reads"].update({
        "ratio": round((stage1[1] / stage1[0]) * (stage2[1] / stage2[0]), 4),
        "center_distance_stage1_mm": module * (stage1[0] + stage1[1]) / 2.0,
        "center_distance_stage2_mm": module * (stage2[0] + stage2[1]) / 2.0,
    })
    return payload


def create_output_shaft(args: dict) -> dict:
    try:
        graph = os_.build_output_shaft_from_dwg_graph()
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_output_shaft", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    return _compose("create_output_shaft", graph, args)


# ------------------------------------------------------------------ 工具注册

_COMMON = {"execute": _TYPE_BOOL, "save_path": _TYPE_STR,
           "expected_volume_mm3": _TYPE_NUM, "include_graph": _TYPE_BOOL}


def create_tools() -> list:
    def spec(name, description, properties, handler):
        schema = {"type": "object", "properties": properties,
                  "additionalProperties": False}
        return ToolSpec(name, description, schema, handler, timeout_s=1800)

    return [
        spec("sw_create_involute_gear",
             "一步到位：渐开线直齿轮 → 生成 Feature Graph → 直接在 SolidWorks 里建出来。"
             "半径量按 ISO 基本齿条自动推出（da=m(z+2)、df=m(z-2.5)、db=d·cosα）。",
             {"module_mm": _TYPE_NUM, "tooth_count": _TYPE_NUM,
              "pressure_angle_deg": _TYPE_NUM, "thickness_mm": _TYPE_NUM,
              "bore_diameter_mm": _TYPE_NUM, "root_fillet_mm": _TYPE_NUM,
              "tip_chamfer_mm": _TYPE_NUM, **_COMMON},
             create_involute_gear),

        spec("sw_create_sphere",
             "一步到位：球体（中心线 + 两段 1/4 圆弧 + 旋转）→ 出图 → 建出来。"
             "判据同时给解析体积 4/3·π·r³ 便于核对。",
             {"diameter_mm": _TYPE_NUM, **_COMMON},
             create_sphere),

        spec("sw_create_parametric_part",
             "一步到位：参数化零件（block / cylinder / tube / flange / stepped_shaft）。",
             {"part_type": _TYPE_STR, "parameters": _TYPE_OBJ, **_COMMON},
             create_parametric_part),

        spec("sw_create_two_stage_reducer",
             "一步到位：两级平行轴减速器（16 个特征）→ 出图 → 建出来。"
             "判据附传动比与两级中心距。",
             {"module_mm": _TYPE_NUM, "pressure_angle_deg": _TYPE_NUM,
              "stage1_teeth": {"type": "array", "items": _TYPE_NUM},
              "stage2_teeth": {"type": "array", "items": _TYPE_NUM},
              "gear_thickness_mm": _TYPE_NUM, "axial_gap_mm": _TYPE_NUM,
              "bore_diameters_mm": {"type": "array", "items": _TYPE_NUM},
              "radial_clearance_mm": _TYPE_NUM, "shaft_extension_mm": _TYPE_NUM,
              **_COMMON},
             create_two_stage_reducer),

        spec("sw_create_output_shaft",
             "一步到位：按《输出轴零件图.DWG》的输出轴（12 个特征、333 mm）→ 出图 → 建出来。",
             dict(_COMMON), create_output_shaft),
    ]
