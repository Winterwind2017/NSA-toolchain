"""SW「一步到位」封装：一次调用 = 生成 Feature Graph + 执行到 SolidWorks。

服务端 `create_*` 是一步（直接建模型），hub 原来只有两半：
`sw_*_plan`（出图）和 `sw_execute_feature_graph`（执行）。
这里把它们缝成一条调用，参数与执行结果都保持可比：

* `execute=false` → 只出图（不需要开 SolidWorks，判据是图的结构）；
* `execute=true`（默认）→ 出图后立刻执行，判据沿用执行器那一套
  （plan_steps / steps_ok / body_volume_mm3 …）。

安全默认：执行器永远**新建文档**，不碰用户已打开的文件（服务端同样语义）。
"""

from __future__ import annotations

import math
from typing import Any

from ..tools import ToolSpec, normalize
from .hubsw import drawing_note as dn
from .hubsw import gear_inspection as gin
from .hubsw import gearbox as gb
from .hubsw import helical_gear as hg
from .hubsw import internal_gear as igr
from .hubsw import involute_gear as ig
from .hubsw import output_shaft as os_
from .hubsw import part_generators as pg
from .hubsw import primitives as pr
from .hubsw import spline as sp
from .hubsw_exec import execute_feature_graph
from .hubsw_feat import _attach
from .hubsw_feat import _check

KIT_KEY = "sw"

_TYPE_NUM = {"type": "number"}
_TYPE_INT = {"type": "integer"}
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
            "body_count": (result.get("reads") or {}).get("body_count"),
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
        # 收尾（齿根圆角 + 齿顶倒角）默认关掉：服务端那一步用 FeatureFillet，
        # 而 SW 2025 已删掉该成员（实测报「找不到成员 -2147352573」）。
        graph = ig.build_involute_gear_graph(
            spec, include_finishing=bool(args.get("include_finishing", False)))
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


def create_internal_gear(args: dict) -> dict:
    module = float(args.get("module_mm", 2.0))
    teeth = int(args.get("tooth_count", 40))
    try:
        spec = igr.validate_internal_gear_spec(
            module_mm=module,
            tooth_count=teeth,
            pressure_angle_deg=float(args.get("pressure_angle_deg", 20.0)),
            thickness_mm=float(args.get("thickness_mm", 12.0)),
            rim_outer_diameter_mm=float(
                args.get("rim_outer_diameter_mm") or module * (teeth + 8.0)),
            profile_shift_x=float(args.get("profile_shift_x", 0.0)))
        graph = igr.build_internal_gear_graph(spec)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_internal_gear", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    payload = _compose("create_internal_gear", graph, args)
    payload["reads"].update({
        "pitch_diameter_mm": round(2 * spec.pitch_radius_mm, 4),
        "tip_diameter_mm": round(2 * spec.tip_radius_mm, 4),
        "root_diameter_mm": round(2 * spec.root_radius_mm, 4),
        "expected_volume_mm3": graph["metadata"]["expected_volume_mm3"],
    })
    return payload


def create_helical_gear(args: dict) -> dict:
    try:
        spec = hg.validate_helical_gear_spec(
            module_normal_mm=float(args.get("module_normal_mm", 2.0)),
            tooth_count=int(args.get("tooth_count", 24)),
            pressure_angle_normal_deg=float(args.get("pressure_angle_deg", 20.0)),
            helix_angle_deg=float(args.get("helix_angle_deg", 20.0)),
            thickness_mm=float(args.get("thickness_mm", 20.0)),
            bore_diameter_mm=float(args.get("bore_diameter_mm", 16.0)),
            slices=int(args.get("slices") or hg.DEFAULT_SLICES))
        graph = hg.build_helical_gear_graph(spec)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_helical_gear", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    payload = _compose("create_helical_gear", graph, args)
    payload["reads"].update({
        "module_transverse_mm": round(spec.module_transverse_mm, 6),
        "lead_mm": round(spec.lead_mm, 4),
        "total_twist_rad": round(spec.total_twist_rad, 6),
        "slices": spec.slices,
        "approximation": "lamina stack",
    })
    return payload


def create_spline_shaft(args: dict) -> dict:
    try:
        spec = sp.validate_spline_spec(
            outer_diameter_mm=float(args.get("outer_diameter_mm", 46.0)),
            inner_diameter_mm=float(args.get("inner_diameter_mm", 40.0)),
            tooth_count=int(args.get("tooth_count", 8)),
            key_width_mm=float(args.get("key_width_mm", 8.0)),
            length_mm=float(args.get("length_mm", 60.0)))
        graph = sp.build_spline_shaft_graph(spec)
    except Exception as exc:                                   # noqa: BLE001
        return normalize(KIT_KEY, "create_spline_shaft", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])
    payload = _compose("create_spline_shaft", graph, args)
    payload["reads"].update({
        "section_area_mm2": graph["metadata"]["section_area_mm2"],
        "expected_volume_mm3": graph["metadata"]["expected_volume_mm3"],
    })
    return payload

def _build_inspection(args: dict) -> tuple[dict, str, list[str]]:
    """按 kind 算检验报告，返回 (report, note_text, 必须出现的数值)。"""
    kind = str(args.get("kind") or "gear").strip().lower()
    pin = args.get("pin_diameter_mm")
    modules = float(args.get("module_mm", 2.0))
    teeth = int(args.get("tooth_count", 20))
    alpha = float(args.get("pressure_angle_deg", 20.0))
    thickness = float(args.get("thickness_mm", 10.0))
    bore = float(args.get("bore_diameter_mm", 10.0))
    shift = float(args.get("profile_shift_x", 0.0))

    if kind == "reducer":
        meta = gb.build_two_stage_reducer_graph(
            module_mm=modules, pressure_angle_deg=alpha,
            gear_thickness_mm=thickness,
            bore_diameters_mm=tuple(float(x) for x in
                                    (args.get("bore_diameters_mm") or [10.0, 12.0, 14.0])),
            axial_gap_mm=float(args.get("axial_gap_mm", 8.0)))["metadata"]
        report = dict(meta)
        report["kind"] = "two_stage_parallel_shaft_reducer"
    elif kind == "spline":
        spec = sp.validate_spline_spec(
            outer_diameter_mm=float(args.get("outer_diameter_mm", 46.0)),
            inner_diameter_mm=float(args.get("inner_diameter_mm", 40.0)),
            tooth_count=int(args.get("tooth_count", 8)),
            key_width_mm=float(args.get("key_width_mm", 8.0)),
            length_mm=float(args.get("length_mm", 60.0)))
        report = sp.spline_inspection(spec, float(pin) if pin else None)
    elif kind == "helical":
        spec = hg.validate_helical_gear_spec(
            module_normal_mm=float(args.get("module_normal_mm", 2.0)),
            tooth_count=teeth, pressure_angle_normal_deg=alpha,
            helix_angle_deg=float(args.get("helix_angle_deg", 20.0)),
            thickness_mm=float(args.get("thickness_mm", 20.0)),
            bore_diameter_mm=float(args.get("bore_diameter_mm", 16.0)),
            slices=int(args.get("slices") or hg.DEFAULT_SLICES))
        report = gin.helical_gear_inspection(spec, float(pin) if pin else None)
    elif kind == "internal":
        ring = igr.validate_internal_gear_spec(
            module_mm=modules, tooth_count=teeth, pressure_angle_deg=alpha,
            thickness_mm=float(args.get("thickness_mm", 12.0)),
            rim_outer_diameter_mm=float(
                args.get("rim_outer_diameter_mm") or modules * (teeth + 8.0)),
            profile_shift_x=shift)
        report = gin.internal_gear_inspection(ring, float(pin) if pin else None)
    else:
        gear = ig.validate_gear_spec(
            module_mm=modules, tooth_count=teeth, pressure_angle_deg=alpha,
            thickness_mm=thickness, bore_diameter_mm=bore,
            root_fillet_mm=min(0.45, modules * 0.225),
            tip_chamfer_mm=min(0.25, modules * 0.125),
            profile_shift_x=shift)
        report = gin.external_gear_inspection(gear, float(pin) if pin else None)

    return report, dn.note_text(report), dn.required_numbers(report)

def inspection_note(args: dict) -> dict:
    """把齿轮/花键的检验尺寸写成工程图注释（并读回校验）。"""
    kind = str(args.get("kind") or "gear").strip().lower()
    write = args.get("write", True) is not False
    x = float(args.get("x", 0.06))
    y = float(args.get("y", 0.10))

    try:
        report, text, numbers = _build_inspection(args)
    except Exception as exc:                                # noqa: BLE001
        return normalize(KIT_KEY, "inspection_note", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])

    numbers = dn.required_numbers(report)
    checks = [_check("note_has_lines", len(text.splitlines()), ">= 3",
                     len(text.splitlines()) >= 3),
              _check("note_contains_key_numbers", len(numbers), ">= 2",
                     len(numbers) >= 2 and all(number in text for number in numbers))]

    reads: dict[str, Any] = {
        "kind": report.get("kind"),
        "note_text": text,
        "required_numbers": numbers,
        "written": False,
    }
    errors: list[str] = []

    if write:
        try:
            try:
                app, current = _attach()
            except Exception:                            # noqa: BLE001
                # 没有打开的文档时也要能画：只附加应用，随后新建一张图纸
                import win32com.client as _w32
                from .hubsw_feat import _solidworks_running
                if not _solidworks_running():
                    raise
                app = _w32.Dispatch("SldWorks.Application")
                current = app.ActiveDoc
            doc, created = dn.ensure_drawing(app, current)
            landing = dn.insert_note(doc, text, x, y)
            readback = landing.get("text") or ""
            reads.update({
                "written": bool(landing.get("ok")),
                "drawing_created": created,
                "document_type": landing.get("type"),
                "note_readback": readback,
                "note_position": landing.get("position"),
            })
            checks += [
                _check("drawing_document", landing.get("type"), 3,
                       landing.get("type") == 3),
                _check("note_text_readback", bool(readback), True, bool(readback)),
                _check("readback_contains_numbers", len(numbers), "all present",
                       bool(numbers) and all(number in readback for number in numbers)),
                _check("note_position_set", landing.get("position"), "not None",
                       bool(landing.get("position"))),
            ]
            if not landing.get("ok"):
                errors.append(landing.get("error") or "插入注释失败")
        except Exception as exc:                            # noqa: BLE001
            errors.append("%s: %s" % (type(exc).__name__, exc))

    ok = all(c.get("ok") for c in checks) and not errors
    return normalize(KIT_KEY, "inspection_note", ok=ok, reads=reads,
                     checks=checks, errors=errors)

def inspection_drawing(args: dict) -> dict:
    """一条龙出"齿轮检验图"：视图 + 标题栏 + 检验注释（并读回校验）。"""
    title = str(args.get("title") or "齿轮检验图")
    number = str(args.get("drawing_number") or "NSA-0001")
    scale = str(args.get("scale") or "1:1")
    material = str(args.get("material") or "45")

    try:
        report, text, numbers = _build_inspection(args)
        title_lines = dn.title_block_lines(title, number, scale, material)
    except Exception as exc:                                # noqa: BLE001
        return normalize(KIT_KEY, "inspection_drawing", ok=False,
                         errors=["%s: %s" % (type(exc).__name__, exc)])

    reads: dict[str, Any] = {"kind": report.get("kind"), "note_text": text,
                             "views": [], "notes": []}
    checks: list = []
    errors: list[str] = []

    try:
        try:
            app, part = _attach()
        except Exception:                                   # noqa: BLE001
            import win32com.client as _w32
            from .hubsw_feat import _solidworks_running
            if not _solidworks_running():
                raise
            app = _w32.Dispatch("SldWorks.Application")
            part = app.ActiveDoc
        # 没有可用零件时，按 kind 现建一个（让这条工具能一条龙跑通）
        usable = part is not None and int(dn._val(part, "GetType") or 0) == 1
        if not usable and args.get("auto_part", True):
            kind_value = str(args.get("kind") or "gear").strip().lower()
            builder = {
                "gear": create_involute_gear,
                "helical": create_helical_gear,
                "internal": create_internal_gear,
                "spline": create_spline_shaft,
                "reducer": create_two_stage_reducer,
            }.get(kind_value)
            if builder is not None:
                builder(dict(args, execute=True))
                part = app.ActiveDoc
                usable = part is not None and int(dn._val(part, "GetType") or 0) == 1
        if not usable:
            raise RuntimeError("没有可用的零件文档（type=%s）：先建零件或让 auto_part=true"
                               % dn._val(part, "GetType"))

        part_path = str(dn._val(part, "GetPathName") or "")
        if not part_path:
            import os as _os
            import time as _time
            folder = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
                _os.path.abspath(__file__)))), "_runs", "inspection_sheet")
            _os.makedirs(folder, exist_ok=True)
            part_path = _os.path.join(
                folder, "insp_%d.SLDPRT" % int(_time.time()))
            # SaveAs4 的第 4/5 参是 byref VARIANT，传 None 会「类型不匹配」；
            # SaveAs 一步到位（本机实测返回 True 且落盘）。
            try:
                part.SaveAs(part_path)
            except Exception:                        # noqa: BLE001
                part.SaveAs4(part_path, 0, 1, None, None)
            if not _os.path.isfile(part_path):
                raise RuntimeError("零件另存失败：%s 没落盘" % part_path)
            part_path = str(dn._val(part, "GetPathName") or part_path)

        active = app.ActiveDoc
        if int(dn._val(active, "GetType") or 0) == 3:
            drawing, created = active, False
        else:
            drawing, created = dn.ensure_drawing(app, None)
        reads["drawing_created"] = created

        placed = []
        # 本机中文模板只认本地化视图名（*Front 返回 None，*前视 才建得出来）
        for names, (vx, vy) in ((["*前视", "*Front"], (0.12, 0.16)),
                                (["*上视", "*Top"], (0.42, 0.16))):
            for view_name in names:
                try:
                    view = drawing.CreateDrawViewFromModelView3(
                        part_path, view_name, vx, vy, 0.0)
                except Exception:                        # noqa: BLE001
                    view = None
                if view is not None:
                    placed.append(view_name)
                    break
        reads["views"] = placed
        checks.append(_check("views_placed", len(placed), ">= 1", bool(placed)))

        inspection = dn.insert_note(drawing, text, 0.10, 0.30)
        block = dn.insert_note(drawing, "\n".join(title_lines), 0.45, 0.02)
        reads["notes"] = [inspection.get("text") or "", block.get("text") or ""]
        reads["document_type"] = inspection.get("type")
        checks += [
            _check("inspection_note_readback", bool(inspection.get("text")), True,
                   bool(inspection.get("text"))),
            _check("inspection_note_has_numbers", len(numbers), "all present",
                   bool(numbers) and all(n in (inspection.get("text") or "")
                                         for n in numbers)),
            _check("title_block_readback", bool(block.get("text")), True,
                   bool(block.get("text"))),
            _check("title_block_has_number", number in (block.get("text") or ""), True,
                   number in (block.get("text") or "")),
        ]
    except Exception as exc:                                # noqa: BLE001
        errors.append("%s: %s" % (type(exc).__name__, exc))

    ok = bool(checks) and all(c.get("ok") for c in checks) and not errors
    return normalize(KIT_KEY, "inspection_drawing", ok=ok, reads=reads,
                     checks=checks, errors=errors)

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
              "tip_chamfer_mm": _TYPE_NUM,
              # 默认 false：SW2025 没有 FeatureFillet，收尾那步必失败
              "include_finishing": _TYPE_BOOL, **_COMMON},
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
             "一步到位：两级平行轴减速器（16 个特征，渐开线齿轮）→ 出图 → 建出来。"
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
             "一步到位：按《输出轴零件图.DWG》的输出轴（13 个特征、333 mm）→ 出图 → 建出来。",
             dict(_COMMON), create_output_shaft),
        spec("sw_create_internal_gear",
             "一步到位：内齿圈（3 个特征，齿顶朝内）→ 出图 → 建出来。"
             "判据附四个特征圆直径与解析体积。",
             {"module_mm": _TYPE_NUM, "tooth_count": _TYPE_INT,
              "pressure_angle_deg": _TYPE_NUM, "thickness_mm": _TYPE_NUM,
              "rim_outer_diameter_mm": _TYPE_NUM, "profile_shift_x": _TYPE_NUM,
              **_COMMON},
             create_internal_gear),

        spec("sw_create_helical_gear",
             "一步到位：斜齿轮（分层近似，默认 8 片）→ 出图 → 建出来。"
             "判据附端面模数、导程、整圈扭转角。",
             {"module_normal_mm": _TYPE_NUM, "tooth_count": _TYPE_INT,
              "pressure_angle_deg": _TYPE_NUM, "helix_angle_deg": _TYPE_NUM,
              "thickness_mm": _TYPE_NUM, "bore_diameter_mm": _TYPE_NUM,
              "slices": _TYPE_INT, **_COMMON},
             create_helical_gear),

        spec("sw_create_spline_shaft",
             "一步到位：矩形花键轴（GB/T 1144，3 个特征）→ 出图 → 建出来。"
             "判据附截面积与解析体积。",
             {"outer_diameter_mm": _TYPE_NUM, "inner_diameter_mm": _TYPE_NUM,
              "tooth_count": _TYPE_INT, "key_width_mm": _TYPE_NUM,
              "length_mm": _TYPE_NUM, **_COMMON},
             create_spline_shaft),

        spec("sw_inspection_note",
             "把齿轮/花键的检验尺寸（公法线、跨棒距、量球/量柱直径、齿厚）写成工程图注释；"
             "没有工程图就新建一张。判据是**注释文本读回**里真的出现这些数值。"
             "kind=gear|helical|internal|spline；write=false 只返回注释文本。",
             {"kind": _TYPE_STR, "write": _TYPE_BOOL, "x": _TYPE_NUM, "y": _TYPE_NUM,
              "module_mm": _TYPE_NUM, "module_normal_mm": _TYPE_NUM,
              "tooth_count": _TYPE_INT, "pressure_angle_deg": _TYPE_NUM,
              "helix_angle_deg": _TYPE_NUM, "profile_shift_x": _TYPE_NUM,
              "thickness_mm": _TYPE_NUM, "bore_diameter_mm": _TYPE_NUM,
              "rim_outer_diameter_mm": _TYPE_NUM, "pin_diameter_mm": _TYPE_NUM,
              "slices": _TYPE_INT, "outer_diameter_mm": _TYPE_NUM,
              "inner_diameter_mm": _TYPE_NUM, "key_width_mm": _TYPE_NUM,
              "length_mm": _TYPE_NUM},
             inspection_note),

        spec("sw_inspection_drawing",
             "一条龙出齿轮检验图：把零件另存 → 新建工程图 → 放前视/上视 → 写检验注释与标题栏，"
             "并读回校验（视图数、注释文本含关键数值、标题栏含图号）。kind 同 sw_inspection_note。",
             {"kind": _TYPE_STR, "title": _TYPE_STR, "drawing_number": _TYPE_STR,
              "scale": _TYPE_STR, "material": _TYPE_STR,
              "module_mm": _TYPE_NUM, "module_normal_mm": _TYPE_NUM,
              "tooth_count": _TYPE_INT, "pressure_angle_deg": _TYPE_NUM,
              "helix_angle_deg": _TYPE_NUM, "profile_shift_x": _TYPE_NUM,
              "thickness_mm": _TYPE_NUM, "bore_diameter_mm": _TYPE_NUM,
              "rim_outer_diameter_mm": _TYPE_NUM, "pin_diameter_mm": _TYPE_NUM,
              "slices": _TYPE_INT, "outer_diameter_mm": _TYPE_NUM,
              "inner_diameter_mm": _TYPE_NUM, "key_width_mm": _TYPE_NUM,
              "length_mm": _TYPE_NUM, "bore_diameters_mm": {"type": "array"},
              "axial_gap_mm": _TYPE_NUM},
             inspection_drawing),
    ]
