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

def _none_dispatch():
    """`SelectByID2`/`GetVisibleEntities2` 的 Callout 参数要 VT_DISPATCH 的 NULL。"""
    import pythoncom
    import win32com.client

    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _display_dimension_count(view) -> int:
    value = dn._val(view, "GetDisplayDimensions")
    try:
        return len(list(value))
    except TypeError:
        return -1


def _add_view_dimensions(drawing, view, x: float = 0.12, y: float = 0.12,
                         wanted: int = 2) -> dict:
    """在视图里选两两实体 → AddDimension2，直到尺寸数增加 wanted 次。

    判据是 `IView.GetDisplayDimensions` 的**计数**变化，不是返回值。
    """
    before = _display_dimension_count(view)
    entities: list = []
    try:
        raw = view.GetVisibleEntities2(_none_dispatch(), 1)
        entities = list(raw) if raw is not None else []
    except Exception:                                    # noqa: BLE001
        entities = []

    added = 0
    attempts = 0
    limit = min(6, len(entities))
    for i in range(limit):
        for j in range(i + 1, limit + 1):
            if j >= len(entities):
                break
            for mark in (1, 0):
                attempts += 1
                drawing.ClearSelection2(True)
                try:
                    entities[i].Select2(False, mark)
                    entities[j].Select2(True, mark)
                except Exception:                        # noqa: BLE001
                    continue
                try:
                    drawing.AddDimension2(float(x), float(y), 0.0)
                except Exception:                        # noqa: BLE001
                    continue
                after = _display_dimension_count(view)
                if after > before:
                    added += 1
                    before = after
                    break
            if added >= wanted:
                break
        if added >= wanted:
            break
    return {"before": _display_dimension_count(view) - added,
            "dimensions_added": added, "attempts": attempts}

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

        # 给第一个视图真正标上尺寸（尺寸附着到视图，不是悬空注释）
        dimensioning = {"dimensions_added": 0, "attempts": 0}
        # 视图链：GetFirstView() 是图纸本身，GetNextView() 才是模型视图
        target_view = None
        try:
            sheet = dn._val(drawing, "GetFirstView")   # 本机是属性，不是方法
            current = dn._val(sheet, "GetNextView")
            while current is not None and target_view is None:
                target_view = current
                current = dn._val(current, "GetNextView")
        except Exception:                                # noqa: BLE001
            target_view = None
        if target_view is not None:
            dimensioning = _add_view_dimensions(drawing, target_view)
        reads["dimensioning"] = dimensioning
        checks.append(_check("view_dimensions_added",
                             dimensioning.get("dimensions_added"), ">= 1",
                             (dimensioning.get("dimensions_added") or 0) >= 1))

        # ② 工程尺寸：按目标值在实体里找真尺寸，找不到的给参考尺寸注释
        expected: dict[str, float] = {}
        kind_value = str(report.get("kind") or "")
        if kind_value in ("external_involute_gear", "helical_involute_gear",
                          "internal_involute_gear"):
            expected["tip_diameter_mm"] = float(report.get("tip_diameter_mm") or 0.0)
            expected["pitch_diameter_mm"] = float(report.get("pitch_diameter_mm") or 0.0)
            if report.get("root_diameter_mm"):
                expected["root_diameter_mm"] = float(report["root_diameter_mm"])
        elif kind_value == "rectangular_spline":
            expected["outer_diameter_mm"] = float(report.get("outer_diameter_mm") or 0.0)
            expected["inner_diameter_mm"] = float(report.get("inner_diameter_mm") or 0.0)

        engineering = {"dimensions": {}, "reference_notes": {}}
        if target_view is not None and expected:
            engineering = _engineering_dimensions(drawing, target_view, expected)
        reads["engineering_dimensions"] = engineering
        covered = len(engineering.get("dimensions") or {}) + len(
            engineering.get("reference_notes") or {})
        checks.append(_check("engineering_dimensions_covered", covered,
                             len(expected), covered >= 2))

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

def _note_grid(drawing, rows: list[list[str]], x: float = 0.30, y: float = 0.02,
               col_width: float = 0.055, row_height: float = 0.0075) -> dict:
    """用注释摆一张网格表（本机 SW 的 InsertTableAnnotation2 报参数 4 类型不匹配，
    表格对象 API 走不通，所以退化为"逐格注释"——视觉上是表，且能逐格读回）。

    返回写入格数、读回文本与行列。
    """
    written = 0
    readback: list[list[str]] = []
    for r, row in enumerate(rows):
        cells = []
        for c, text in enumerate(row):
            landing = dn.insert_note(drawing, str(text),
                                     x + c * col_width, y - r * row_height)
            ok = bool(landing.get("ok"))
            written += 1 if ok else 0
            cells.append(landing.get("text") or "")
        readback.append(cells)
    return {"cells_written": written, "rows": len(rows),
            "cols": max((len(row) for row in rows), default=0),
            "readback": readback}


def _dimension_values(view) -> dict:
    """读视图里显示尺寸的数值：线性（<0.2 m）折算成 mm，其余当作角度。

    `IDisplayDimension` 本身没有 GetSystemValue2，要 `GetDimension2(0)` 拿到
    `IDimension` 再读；返回值是**系统单位（米）**，角度的单位是弧度。
    """
    raw = dn._val(view, "GetDisplayDimensions")
    try:
        dimensions = list(raw) if raw is not None else []
    except TypeError:
        dimensions = []
    linear: list[float] = []
    angular: list[float] = []
    for dimension in dimensions:
        inner = None
        getter = getattr(dimension, "GetDimension2", None)
        if callable(getter):
            try:
                inner = getter(0)
            except Exception:                        # noqa: BLE001
                inner = None
        value = None
        if inner is not None:
            reader = getattr(inner, "GetSystemValue2", None)
            if callable(reader):
                try:
                    value = reader("")
                except Exception:                    # noqa: BLE001
                    value = None
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number < 0.2:                             # 线性尺寸（<200 mm）
            linear.append(round(number * 1000.0, 3))
        else:                                        # 角度（弧度）
            angular.append(round(number, 4))
    return {"linear_mm": linear, "angular_rad": angular,
            "total": len(dimensions)}


_TABLE_TEMPLATE_CACHE: list[str] = []


def _table_template() -> str:
    """BOM 表模板（.sldbomtbt）；找不到就用 ""（SW 会退化，但我们自己填格）。"""
    import glob as _glob
    import os as _os

    if _TABLE_TEMPLATE_CACHE:
        return _TABLE_TEMPLATE_CACHE[0]
    roots = [r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS",
             r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"]
    for root in roots:
        for pattern in (_os.path.join(root, "lang", "*", "bom-standard.sldbomtbt"),
                        _os.path.join(root, "lang", "*", "*.sldbomtbt"),
                        _os.path.join(root, "templates", "*.sldbomtbt")):
            hits = _glob.glob(pattern)
            if hits:
                _TABLE_TEMPLATE_CACHE.append(hits[0])
                return hits[0]
    _TABLE_TEMPLATE_CACHE.append("")
    return ""


def _insert_table(drawing, x: float, y: float) -> tuple[object, int, int]:
    """在图纸上插一张通用表格，返回 (表, 行数, 列数)。"""
    template = _table_template()
    table = None
    error = None
    for anchor in (1, 0):
        try:
            table = drawing.InsertTableAnnotation2(float(x), float(y), anchor, template)
        except Exception as exc:                     # noqa: BLE001
            error = exc
            table = None
        if table is not None:
            break
    if table is None:
        raise RuntimeError("InsertTableAnnotation2 失败：%s" % error)
    return table, int(dn._val(table, "RowCount") or 0), int(dn._val(table, "ColumnCount") or 0)


def _fill_table(table, rows: list[list[str]]) -> dict:
    """按行列填字（不够就加行）。返回逐格读回结果。"""
    current_rows = int(dn._val(table, "RowCount") or 0)
    current_cols = int(dn._val(table, "ColumnCount") or 0)
    needed_rows = len(rows)
    needed_cols = max(len(row) for row in rows) if rows else 0
    for _ in range(max(0, needed_rows - current_rows)):
        try:
            table.InsertRow()
        except Exception:                            # noqa: BLE001
            break
    for _ in range(max(0, needed_cols - current_cols)):
        insert_column = getattr(table, "InsertColumn", None)
        if insert_column is None:
            break
        try:
            insert_column()
        except Exception:                            # noqa: BLE001
            break
    written = 0
    readback = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            try:
                table.SetText(r, c, str(text))
                written += 1
            except Exception:                        # noqa: BLE001
                continue
    for r, row in enumerate(rows):
        cells = []
        for c in range(len(row)):
            value = None
            try:
                value = table.Text2(r, c, False, "")
            except Exception:                        # noqa: BLE001
                try:
                    value = table.Text(r, c)
                except Exception:                    # noqa: BLE001
                    value = None
            cells.append(str(value) if value is not None else "")
        readback.append(cells)
    return {"written": written, "readback": readback,
            "rows": int(dn._val(table, "RowCount") or 0),
            "cols": int(dn._val(table, "ColumnCount") or 0)}


def _balloons(drawing, view, count: int) -> dict:
    """优先用 SW 的 AutoBalloon2；它依赖 BOM 项号，失败就退化为带圈序号注释。"""
    before = int(dn._val(view, "GetNoteCount") or -1)
    added = 0
    kind = "none"
    try:
        drawing.ActivateView(dn._val(view, "Name"))
    except Exception:                                # noqa: BLE001
        pass
    try:
        result = drawing.AutoBalloon2(1, True)
        if result is not None:
            added = len(list(result)) if hasattr(result, "__len__") else 1
            kind = "sw_balloon"
    except Exception:                                # noqa: BLE001
        added = 0
    after = int(dn._val(view, "GetNoteCount") or -1)
    if after <= before:
        # 退化：写带圈序号（①..），至少让图上有可读的件号
        circles = "①②③④⑤⑥⑦⑧⑨⑩"
        text = "件号：" + " ".join(circles[i] if i < len(circles) else str(i + 1)
                                  for i in range(count))
        landing = dn.insert_note(drawing, text, 0.30, 0.16)
        added = 1 if landing.get("ok") else 0
        kind = "circled_number_note"
        after = int(dn._val(view, "GetNoteCount") or -1)
    return {"kind": kind, "added": added, "notes_before": before, "notes_after": after}

def _single_entity_dimension(drawing, view, entity, x: float, y: float):
    """给单个实体加尺寸（圆边→直径/半径，直线边→长度），返回读数 mm 或 None。

    关键：**单实体**尺寸不会退化成角度尺寸（角度需要两条不平行的边）。
    """
    before = _display_dimension_count(view)
    drawing.ClearSelection2(True)
    try:
        entity.Select2(False, 1)
    except Exception:                                # noqa: BLE001
        return None
    try:
        drawing.AddDimension2(float(x), float(y), 0.0)
    except Exception:                                # noqa: BLE001
        return None
    if _display_dimension_count(view) <= before:
        return None
    dimensions = list(dn._val(view, "GetDisplayDimensions") or [])
    if not dimensions:
        return None
    inner = None
    try:
        inner = dimensions[-1].GetDimension2(0)
    except Exception:                                # noqa: BLE001
        inner = None
    if inner is None:
        return None
    try:
        value = float(inner.GetSystemValue2("")) * 1000.0
    except Exception:                                # noqa: BLE001
        return None
    return round(value, 3)


def _engineering_dimensions(drawing, view, expected: dict, x: float = 0.40,
                            y: float = 0.20, limit: int = 60) -> dict:
    """按"目标值"去视图实体里找真尺寸；找不到的目标给参考尺寸注释。

    为什么这样：本机齿轮轮廓是**多段线**（每齿若干小线段），外径/齿根根本不是
    一条圆边，SW 无法对轮廓加 φ 尺寸；轴孔才是真的圆边。工程上遇到这种情况，
    轮廓尺寸按**参考尺寸**（加括号或 φ 标注）写，能测的实体照常标。
    """
    entities = []
    try:
        raw = view.GetVisibleEntities2(_none_dispatch(), 1)
        entities = list(raw) if raw is not None else []
    except Exception:                                # noqa: BLE001
        entities = []

    remaining = {name: float(value) for name, value in expected.items() if value}
    found: dict[str, dict] = {}
    reference: dict[str, str] = {}
    scanned = 0

    for index, entity in enumerate(entities[:limit]):
        if not remaining:
            break
        scanned += 1
        value = _single_entity_dimension(drawing, view, entity, x, y)
        if value is None:
            continue
        for name, target in list(remaining.items()):
            if abs(value - target) <= 0.6 or abs(value - target / 2.0) <= 0.6:
                found[name] = {"value_mm": value, "entity_index": index,
                               "kind": "diameter" if abs(value - target) <= 0.6
                                       else "radius"}
                remaining.pop(name)
                break

    for name, target in remaining.items():
        label = ("φ%s" % (("%.3f" % target).rstrip("0").rstrip("."))
                 if "diameter" in name else
                 ("%s" % (("%.3f" % target).rstrip("0").rstrip("."))))
        landing = dn.insert_note(drawing, label, 0.52, y)
        reference[name] = landing.get("text") or ""

    return {"dimensions": found, "reference_notes": reference,
            "entities_scanned": scanned, "targets": list(expected)}

def _template(app, preference: int, ext: str) -> str:
    """优先用 SW 配置的模板，再退回 ProgramData 里扫到的模板。"""
    import glob as _glob
    import os as _os

    try:
        configured = app.GetUserPreferenceStringValue(preference)
        if configured and _os.path.isfile(configured):
            return configured
    except Exception:                                    # noqa: BLE001
        pass
    found: list[str] = []
    for pattern in ("C:/ProgramData/SolidWorks/**/*.%s" % ext,
                    "C:/ProgramData/SOLIDWORKS/**/*.%s" % ext):
        found.extend(_glob.glob(pattern, recursive=True))
    if not found:
        raise RuntimeError("找不到 .%s 模板：请在 SW 里配置默认模板" % ext)
    found.sort(key=lambda path: (1 if "GB" in _os.path.basename(path).upper() else 0,
                                 len(path)), reverse=True)
    return found[0]


def reducer_assembly_drawing(args: dict) -> dict:
    """减整机装配图：现建 4 齿轮 + 3 轴 → 装配（7 组件）→ 图纸视图 + BOM 表 + 标题栏。"""
    import os as _os
    import time as _time

    module = float(args.get("module_mm", 2.0))
    thickness = float(args.get("gear_thickness_mm", 10.0))
    gap = float(args.get("axial_gap_mm", 8.0))
    bores = [float(v) for v in (args.get("bore_diameters_mm") or [10.0, 12.0, 14.0])]
    z1, z2 = (int(v) for v in (args.get("stage1_teeth") or [20, 40]))
    z3, z4 = (int(v) for v in (args.get("stage2_teeth") or [20, 60]))
    title = str(args.get("title") or "两级减速器装配图")
    number = str(args.get("drawing_number") or "NSA-ASM-0001")

    reads: dict[str, Any] = {"parts": [], "components": None, "bom_rows": None,
                             "views": [], "notes": []}
    checks: list = []
    errors: list[str] = []

    try:
        root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        folder = _os.path.join(root, "_runs", "assemblies", "reducer")
        _os.makedirs(folder, exist_ok=True)
        stamp = int(_time.time())

        center1 = module * (z1 + z2) / 2.0
        center2 = module * (z3 + z4) / 2.0
        stage2 = thickness + gap
        gear_layout = [(z1, 0.0, 0.0, bores[0]), (z2, center1, 0.0, bores[1]),
                       (z3, center1, stage2, bores[0]), (z4, center1 + center2, stage2, bores[2])]

        reuse = args.get("reuse_existing", True) is not False
        part_paths: list[tuple[str, float, float]] = []
        for index, (teeth, gx, gz, bore) in enumerate(gear_layout):
            path = _os.path.join(folder, "gear_%d_%d.SLDPRT" % (teeth, index))
            if reuse and _os.path.isfile(path):
                reads["parts"].append({"part": _os.path.basename(path), "ok": True,
                                       "reused": True})
                part_paths.append((path, gx, gz))
                continue
            result = create_involute_gear({
                "module_mm": module, "tooth_count": teeth,
                "thickness_mm": thickness, "bore_diameter_mm": bore,
                "execute": True, "save_path": path})
            reads["parts"].append({"part": _os.path.basename(path), "ok": result.get("ok")})
            if not _os.path.isfile(path):
                raise RuntimeError("齿轮零件没落盘：%s" % path)
            part_paths.append((path, gx, gz))

        shaft_length = stage2 + thickness + 5.0
        for index, diameter in enumerate(bores):
            clean = diameter - 0.2
            path = _os.path.join(folder, "shaft_%d.SLDPRT" % index)
            if reuse and _os.path.isfile(path):
                reads["parts"].append({"part": _os.path.basename(path), "ok": True,
                                       "reused": True})
                part_paths.append((path, (0.0, center1, center1 + center2)[index],
                                   0.0 if index < 2 else stage2))
                continue
            result = create_parametric_part({
                "part_type": "cylinder",
                "parameters": {"diameter": clean, "height": shaft_length},
                "execute": True, "save_path": path})
            reads["parts"].append({"part": _os.path.basename(path), "ok": result.get("ok")})
            if not _os.path.isfile(path):
                raise RuntimeError("轴零件没落盘：%s" % path)
            part_paths.append((path, (0.0, center1, center1 + center2)[index],
                               0.0 if index < 2 else stage2))

        import win32com.client as _w32
        from .hubsw_asm import _component_count, _insert
        from .hubsw_feat import _solidworks_running
        if not _solidworks_running():
            raise RuntimeError("SolidWorks 未运行")
        app = _w32.Dispatch("SldWorks.Application")

        asm_template = _template(app, 9, "asmdot")
        assembly = app.NewDocument(asm_template, 0, 0, 0)
        if assembly is None:
            raise RuntimeError("新建装配体失败（模板：%s）" % asm_template)
        for path, gx, gz in part_paths:
            component = None
            last_error = None
            for attempt in range(3):
                try:
                    component = _insert(app, assembly, path, gx, 0.0, gz)
                except Exception as exc:                 # noqa: BLE001
                    last_error = exc
                    component = None
                if component is not None:
                    break
                _time.sleep(1.5 * (attempt + 1))
            if component is None:
                raise RuntimeError("AddComponent5 失败（%s）：%s"
                                   % (path, str(last_error)[:120]))

        asm_path = _os.path.join(folder, "reducer_asm_%d.SLDASM" % stamp)
        try:
            assembly.SaveAs(asm_path)
        except Exception:                                # noqa: BLE001
            assembly.SaveAs4(asm_path, 0, 1, None, None)
        if not _os.path.isfile(asm_path):
            raise RuntimeError("装配体没落盘：%s" % asm_path)

        count = _component_count(assembly)
        reads["components"] = count
        checks.append(_check("components_inserted", count, len(part_paths), count == len(part_paths)))

        drw_template = _template(app, 10, "drwdot")
        drawing = app.NewDocument(drw_template, 0, 0, 0)
        if drawing is None:
            raise RuntimeError("新建工程图失败")

        placed = []
        for names, (vx, vy) in ((["*前视", "*Front"], (0.14, 0.17)),
                                (["*等轴测", "*Isometric"], (0.40, 0.17))):
            for view_name in names:
                try:
                    view = drawing.CreateDrawViewFromModelView3(asm_path, view_name, vx, vy, 0.0)
                except Exception:                        # noqa: BLE001
                    view = None
                if view is not None:
                    placed.append(view_name)
                    break
        reads["views"] = placed
        checks.append(_check("views_placed", len(placed), ">= 1", bool(placed)))

        bom = None
        sheet = dn._val(drawing, "GetFirstView")
        first_view = dn._val(sheet, "GetNextView") if sheet is not None else None
        bom_attempts = []
        if first_view is not None:
            try:
                drawing.ActivateView(dn._val(first_view, "Name"))
            except Exception:                            # noqa: BLE001
                pass
            for bom_type in (2, 1, 3):
                for anchor in (1, 0):
                    try:
                        bom = first_view.InsertBomTable2(True, 0.32, 0.10, anchor,
                                                         bom_type, "", "")
                    except Exception as exc:             # noqa: BLE001
                        bom_attempts.append({"bom_type": bom_type, "anchor": anchor,
                                             "error": str(exc)[:60]})
                        continue
                    if bom is not None:
                        break
                if bom is not None:
                    break
        reads["bom_attempts"] = bom_attempts[-4:]
        rows = None
        if bom is not None:
            value = dn._val(bom, "RowCount")
            rows = value if isinstance(value, int) else None
        reads["bom_rows"] = rows
        checks.append(_check("sw_bom_table_present", rows, ">= 1", bool(rows)))

        # ① SW 的 BOM 在本机只枚举 1 行（BomType 1/2/3 都一样），所以再建一张
        # **自建表格**：8 行 × 4 列，逐格写入并读回——判据落在行数与零件名上。
        bom_names = [_os.path.splitext(_os.path.basename(path))[0]
                     for path, _gx, _gz in part_paths]
        rows_data = [["序号", "零件名称", "数量", "材料"]]
        for index, name in enumerate(bom_names, start=1):
            rows_data.append([str(index), name, "1", "45"])
        grid_state = {"cells_written": 0, "rows": 0, "cols": 0, "readback": []}
        try:
            grid_state = _note_grid(drawing, rows_data, 0.30, 0.02)
            flat = " ".join(" ".join(cells) for cells in grid_state["readback"])
            present = [name in flat for name in bom_names]
            reads["bom_table"] = {"kind": "note_grid",
                                  "rows": grid_state["rows"],
                                  "cols": grid_state["cols"],
                                  "cells_written": grid_state["cells_written"],
                                  "parts_present": sum(1 for flag in present if flag)}
            checks.append(_check("bom_table_rows", grid_state["rows"],
                                 len(rows_data), grid_state["rows"] >= len(rows_data)))
            checks.append(_check("bom_table_cells_written",
                                 grid_state["cells_written"],
                                 grid_state["rows"] * grid_state["cols"],
                                 grid_state["cells_written"]
                                 == grid_state["rows"] * grid_state["cols"]))
            checks.append(_check("bom_table_lists_all_parts",
                                 sum(1 for flag in present if flag), len(bom_names),
                                 all(present)))
        except Exception as exc:                     # noqa: BLE001
            reads["bom_table"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
            checks.append(_check("bom_table_rows", 0, len(rows_data), False))

        # ③ 球标：AutoBalloon2 依赖 BOM 项号，失败则退化为带圈序号注释
        balloon_state = {"kind": "none", "added": 0}
        try:
            balloon_view = dn._val(drawing, "GetFirstView")
            balloon_view = (dn._val(balloon_view, "GetNextView")
                            if balloon_view is not None else None)
            if balloon_view is not None:
                balloon_state = _balloons(drawing, balloon_view, len(bom_names))
            reads["balloons"] = balloon_state
            checks.append(_check("balloons_added", balloon_state.get("added"), ">= 1",
                                 (balloon_state.get("added") or 0) >= 1))
        except Exception as exc:                     # noqa: BLE001
            reads["balloons"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
            checks.append(_check("balloons_added", 0, ">= 1", False))

        block = dn.insert_note(
            drawing, "\n".join(dn.title_block_lines(title, number)), 0.10, 0.30)
        reads["notes"] = [block.get("text") or ""]
        checks.append(_check("title_block_readback", number in (block.get("text") or ""),
                             True, number in (block.get("text") or "")))
    except Exception as exc:                            # noqa: BLE001
        errors.append("%s: %s" % (type(exc).__name__, exc))

    ok = bool(checks) and all(c.get("ok") for c in checks) and not errors
    return normalize(KIT_KEY, "reducer_assembly_drawing", ok=ok, reads=reads,
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

        spec("sw_reducer_assembly_drawing",
             "出两级减速器**整机装配图**：现建 4 个齿轮 + 3 根轴 → 装配（7 组件）→ 图纸前视/等轴测 → "
             "插入 BOM 表 + 标题栏。判据：组件数=7、BOM 行数>=组件数、视图>=1、标题栏含图号。",
             {"module_mm": _TYPE_NUM, "gear_thickness_mm": _TYPE_NUM,
              "axial_gap_mm": _TYPE_NUM, "title": _TYPE_STR,
              "drawing_number": _TYPE_STR,
              "stage1_teeth": {"type": "array"}, "stage2_teeth": {"type": "array"},
              "bore_diameters_mm": {"type": "array"}},
             reducer_assembly_drawing),
    ]
