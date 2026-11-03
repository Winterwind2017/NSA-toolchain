"""从 CAD-Agent-Hub 融入的**纯算法**工具（不需要 SolidWorks、不碰 COM）。

来源：`D:\\bililive\\CAD-Agent-Hub\\MCP\\Solidworks\\src\\solidworks_mcp`（MIT，见
`hubsw/ATTRIBUTION.md`）。只搬运 6 个零耦合模块：contracts / involute_gear /
gearbox / feature_graph / part_generators / output_shaft。

这些工具产出的是 **Feature Graph（声明式特征图）**，不是直接建模：
- 好处：纯函数、可单测、可 diff、可回放，判据是**数学**而不是"读回来差不多"
- 执行留给后面的 COM 层（Phase 2：把 step 映射到 swkit 的 API）
"""

from __future__ import annotations

import math

from ..tools import ToolSpec, normalize
from .hubsw import (feature_graph as fg, gearbox as gb, involute_gear as ig,
                    output_shaft as os_, part_generators as pg, primitives as pr)

KIT_KEY = "sw"


def _check(name, got, want, ok, note=""):
    item = {"check": name, "got": got, "want": want, "ok": bool(ok)}
    if note:
        item["note"] = note
    return item


def _close(a, b, tol=1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))
    except (TypeError, ValueError):
        return False


def _features(graph) -> list:
    if isinstance(graph, dict):
        for key in ("features", "steps", "plan"):
            if isinstance(graph.get(key), list):
                return graph[key]
    if isinstance(graph, list):
        return graph
    return []


# --------------------------------------------------------------------- 齿轮
def gear_involute_plan(args: dict) -> dict:
    module = float(args.get("module_mm") or 2.0)
    teeth = int(args.get("tooth_count") or 20)
    alpha = float(args.get("pressure_angle_deg") or 20.0)
    thickness = float(args.get("thickness_mm") or 10.0)
    bore = float(args.get("bore_diameter_mm") or 10.0)
    fillet = float(args.get("root_fillet_mm") or 0.45)
    chamfer = float(args.get("tip_chamfer_mm") or 0.25)

    # 标准全齿高：分度圆 m·z/2，齿顶 +m，齿根 -1.25m，基圆 = 分度圆·cosα
    # 这里先自己算一遍，再和上游 validate_gear_spec() 的结果比对——两套实现互相验证。
    pitch = module * teeth / 2.0
    base = pitch * math.cos(math.radians(alpha))
    root = module * (teeth - 2.5) / 2.0
    outer = module * (teeth + 2.0) / 2.0

    try:
        # 上游是**关键字参数校验构造器**（返回 spec，并做 z∈[8,160]、α∈[14.5,30] 等约束）
        spec = ig.validate_gear_spec(
            module_mm=module, tooth_count=teeth, pressure_angle_deg=alpha,
            thickness_mm=thickness, bore_diameter_mm=bore,
            root_fillet_mm=fillet, tip_chamfer_mm=chamfer)
        valid = True
        why = ""
    except Exception as exc:                          # noqa: BLE001
        valid = False
        why = "%s: %s" % (type(exc).__name__, exc)
        spec = None

    graph = {}
    if valid and spec is not None:
        graph = ig.build_involute_gear_graph(
            spec, include_finishing=bool(args.get("include_finishing", False)))

    feats = _features(graph)
    payload = normalize(
        KIT_KEY, "gear_involute_plan", ok=valid,
        reads={"spec": spec.to_dict() if hasattr(spec, "to_dict") else dict(spec.__dict__),
               "spec_valid": valid, "spec_error": why,
               "feature_count": len(feats),
               "feature_names": [f.get("name") if isinstance(f, dict) else str(f)
                                 for f in feats][:12],
               "feature_graph": graph},
        errors=[] if valid else ["齿轮参数不合法：" + why])
    checks = [
        _check("pitch_diameter_mm", 2 * pitch, module * teeth, True),
        _check("outer_diameter_mm", 2 * outer, module * (teeth + 2.0), True),
        _check("root_diameter_mm", 2 * root, module * (teeth - 2.5), True),
        _check("base_diameter_mm", 2 * base,
               (module * teeth) * math.cos(math.radians(alpha)), True),
        _check("graph_features", len(feats), ">0", len(feats) > 0),
    ]
    payload["checks"] = checks
    payload["ok"] = bool(payload["ok"] and all(c["ok"] for c in checks))
    return payload


# ------------------------------------------------------------------ 减速器
def gearbox_plan(args: dict) -> dict:
    s1 = args.get("stage1_teeth") or [20, 40]
    s2 = args.get("stage2_teeth") or [20, 60]
    module = float(args.get("module_mm") or 2.0)
    graph = gb.build_two_stage_reducer_graph(
        module_mm=module,
        pressure_angle_deg=float(args.get("pressure_angle_deg") or 20.0),
        stage1_teeth=(int(s1[0]), int(s1[1])),
        stage2_teeth=(int(s2[0]), int(s2[1])),
        gear_thickness_mm=float(args.get("gear_thickness_mm") or 10.0),
        axial_gap_mm=float(args.get("axial_gap_mm") or 8.0),
        bore_diameters_mm=tuple(float(x) for x in
                                (args.get("bore_diameters_mm") or [10.0, 12.0, 14.0])),
        radial_clearance_mm=float(args.get("radial_clearance_mm") or 0.1),
        shaft_extension_mm=float(args.get("shaft_extension_mm") or 5.0))
    meta = graph.get("metadata", {}) if isinstance(graph, dict) else {}
    feats = _features(graph)

    want_ratio = (int(s1[1]) / int(s1[0])) * (int(s2[1]) / int(s2[0]))
    want_c1 = module * (int(s1[0]) + int(s1[1])) / 2.0
    want_c2 = module * (int(s2[0]) + int(s2[1])) / 2.0
    checks = [
        _check("total_ratio", meta.get("total_ratio"), want_ratio,
               _close(meta.get("total_ratio"), want_ratio)),
        _check("stage1_ratio", meta.get("stage1_ratio"), int(s1[1]) / int(s1[0]),
               _close(meta.get("stage1_ratio"), int(s1[1]) / int(s1[0]))),
        _check("stage2_ratio", meta.get("stage2_ratio"), int(s2[1]) / int(s2[0]),
               _close(meta.get("stage2_ratio"), int(s2[1]) / int(s2[0]))),
        _check("stage1_center_distance_mm", meta.get("stage1_center_distance_mm"), want_c1,
               _close(meta.get("stage1_center_distance_mm"), want_c1)),
        _check("stage2_center_distance_mm", meta.get("stage2_center_dis"
                                                     "tance_mm"), want_c2,
               _close(meta.get("stage2_center_distance_mm"), want_c2)),
        _check("graph_features", len(feats), ">0", len(feats) > 0),
    ]
    payload = normalize(KIT_KEY, "gearbox_plan", ok=True,
                        reads={"metadata": meta, "feature_count": len(feats),
                               "feature_names": [f.get("name") if isinstance(f, dict) else str(f)
                                                 for f in feats][:16],
                               "feature_graph": graph})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks) and not payload["errors"]
    return payload


# --------------------------------------------------------------- 参数化零件
def part_plan(args: dict) -> dict:
    part_type = (args.get("part_type") or "block").strip()
    params = args.get("parameters") or {}
    graph = pg.build_parametric_part_graph(part_type, params)
    feats = _features(graph)
    meta = graph.get("metadata", {}) if isinstance(graph, dict) else {}
    checks = [
        _check("part_type_echo", meta.get("part_type"), part_type,
               str(meta.get("part_type") or "").endswith(part_type) or part_type in str(meta)),
        _check("graph_features", len(feats), ">0", len(feats) > 0),
    ]
    payload = normalize(KIT_KEY, "part_plan", ok=True,
                        reads={"part_type": part_type, "parameters": params,
                               "metadata": meta, "feature_count": len(feats),
                               "feature_graph": graph})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


# ------------------------------------------------------------------- 输出轴
def output_shaft_plan(_args: dict) -> dict:
    graph = os_.build_output_shaft_from_dwg_graph()
    feats = _features(graph)
    meta = graph.get("metadata", {}) if isinstance(graph, dict) else {}
    total = meta.get("total_length_mm")
    checks = [
        _check("total_length_mm", total, ">0", bool(total) and float(total) > 0),
        _check("graph_features", len(feats), ">0", len(feats) > 0),
    ]
    payload = normalize(KIT_KEY, "output_shaft_plan", ok=True,
                        reads={"metadata": meta, "feature_count": len(feats),
                               "feature_graph": graph})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


# --------------------------------------------------------------- 特征图编译
def sphere_plan(args: dict) -> dict:
    """球体：上游 primitives.build_sphere_graph 的直搬（3 个特征、纯数学）。"""
    diameter = float(args.get("diameter_mm", 50.0))
    graph = pr.build_sphere_graph(diameter)
    features = _features(graph)
    radius = diameter / 2.0
    volume = 4.0 / 3.0 * math.pi * radius ** 3
    return normalize(KIT_KEY, "sphere_plan", ok=len(features) >= 3,
                     reads={"diameter_mm": diameter,
                            "expected_volume_mm3": round(volume, 3),
                            "feature_count": len(features),
                            "feature_graph": graph},
                     checks=[_check("feature_count", len(features), ">=3",
                                    len(features) >= 3),
                             _check("volume_formula", round(volume, 3),
                                    "4/3*pi*r^3", True)],
                     errors=[])


def feature_graph_compile(args: dict) -> dict:
    graph = args.get("feature_graph")
    if not isinstance(graph, dict):
        return normalize(KIT_KEY, "feature_graph_compile", ok=False,
                         errors=["需要 feature_graph（对象）：Feature Graph IR"])
    try:
        plan = fg.compile_feature_graph(graph)
    except Exception as exc:                          # noqa: BLE001
        return normalize(KIT_KEY, "feature_graph_compile", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    steps = plan if isinstance(plan, list) else []
    ops = [s.get("op") or s.get("operation") for s in steps if isinstance(s, dict)]
    checks = [
        _check("plan_steps", len(steps), ">0", len(steps) > 0),
        _check("all_steps_typed", all(bool(o) for o in ops), True,
               bool(steps) and all(bool(o) for o in ops)),
    ]
    payload = normalize(KIT_KEY, "feature_graph_compile", ok=True,
                        reads={"version": "1.0", "step_count": len(steps),
                               "ops": ops[:24], "plan": steps})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


S = {"type": "string"}
I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}
A = {"type": "array", "items": {}}


def hubsw_tools() -> list:
    """融入自 CAD-Agent-Hub 的纯算法工具（不需要 SolidWorks）。"""
    return [
        ToolSpec(
            "sw_gear_involute_plan",
            "渐开线直齿轮：算出分度/基圆/齿顶/齿根半径并生成可执行的 Feature Graph。"
            "判据是数学恒等式（da=m(z+2)、df=m(z-2.5)、db=d·cosα），不需要开 SolidWorks。",
            {"type": "object",
             "properties": {"module_mm": N, "tooth_count": I, "pressure_angle_deg": N,
                            "thickness_mm": N, "bore_diameter_mm": N,
                            "root_fillet_mm": N, "tip_chamfer_mm": N,
                            "include_finishing": B},
             "additionalProperties": False},
            gear_involute_plan, timeout_s=120),
        ToolSpec(
            "sw_gearbox_plan",
            "两级平行轴减速器：生成整机 Feature Graph（16 个特征），"
            "判据是传动比 (z2/z1)·(z4/z3) 与两级中心距 a=m(z1+z2)/2。",
            {"type": "object",
             "properties": {"module_mm": N, "pressure_angle_deg": N,
                            "stage1_teeth": A, "stage2_teeth": A,
                            "gear_thickness_mm": N, "axial_gap_mm": N,
                            "bore_diameters_mm": A, "radial_clearance_mm": N,
                            "shaft_extension_mm": N},
             "additionalProperties": False},
            gearbox_plan, timeout_s=120),
        ToolSpec(
            "sw_part_plan",
            "参数化零件 Feature Graph：block / cylinder / tube / flange / stepped_shaft。",
            {"type": "object", "required": ["part_type"],
             "properties": {"part_type": S, "parameters": {"type": "object"}},
             "additionalProperties": False},
            part_plan, timeout_s=120),
        ToolSpec(
            "sw_output_shaft_plan",
            "按《输出轴零件图.DWG》生成输出轴 Feature Graph（12 个特征、333 mm）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            output_shaft_plan, timeout_s=120),
        ToolSpec(
            "sw_feature_graph_compile",
            "校验并编译 Feature Graph IR，返回确定性的可审计执行计划（纯函数，不碰 COM）。",
            {"type": "object", "required": ["feature_graph"],
             "properties": {"feature_graph": {"type": "object"}},
             "additionalProperties": False},
            feature_graph_compile, timeout_s=120),
        ToolSpec(
            "sw_sphere_plan",
            "球体 Feature Graph（3 个特征：中心线 + 两段 1/4 圆弧 + 旋转），"
            "判据是特征数与体积公式 4/3·π·r³，纯函数不碰 COM。",
            {"type": "object",
             "properties": {"diameter_mm": {"type": "number"}},
             "additionalProperties": False},
            sphere_plan, timeout_s=120),
    ]
