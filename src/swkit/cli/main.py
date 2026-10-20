"""swkit.cli —— 命令行入口

    swkit status                       连接状态 + 注册表摘要
    swkit registry [--status verified] 列出工具及其判据
    swkit info                         当前文档概览
    swkit pattern-component --kind linear --count 3 --spacing 0.05
    swkit mirror-component --plane 前视基准面
    swkit selftest                     import/注册表/COM 三层自检

设计上刻意**只做已验证的动作**；未复核的高层 API 走 `swkit api <op>` 且会打印 unverified。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional


def _dump(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _app():
    from ..core.com import dispatch
    return dispatch("SldWorks.Application")


def _doc(app):
    from ..core.com import pyw
    doc = app.ActiveDoc
    return pyw().Dispatch(doc) if doc is not None else None


# ── 子命令 ────────────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    from .. import __version__
    from ..core.com import val
    from ..registry import summary
    out: Dict[str, Any] = {"swkit_version": __version__, "registry": summary()}
    try:
        app = _app()
        out.update({
            "connected": True,
            "revision": str(val(app, "RevisionNumber", "")),
            "open_documents": int(val(app, "GetDocumentCount", 0) or 0),
            "active_document": str(val(app, "GetTitle", "") or ""),
        })
    except Exception as exc:
        out.update({"connected": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    _dump(out)
    return 0 if out.get("connected") else 2


def cmd_registry(args: argparse.Namespace) -> int:
    from ..registry import REGISTRY, summary
    rows: List[Dict[str, str]] = []
    for entry in REGISTRY.values():
        if args.status and entry.status != args.status:
            continue
        if args.implemented and not entry.implemented:
            continue
        rows.append({"name": entry.name, "group": entry.group, "status": entry.status,
                     "implemented": entry.implemented, "api": entry.api,
                     "evidence": entry.evidence, "note": entry.note})
    rows.sort(key=lambda r: (not r["implemented"], r["status"] != "verified",
                             r["group"], r["name"]))
    if args.json:
        _dump({"count": len(rows), "summary": summary(), "tools": rows})
        return 0
    print("%-34s %-10s %-11s %-13s %s" % ("工具", "状态", "已编码", "分组", "依据"))
    print("-" * 122)
    for r in rows:
        print("%-34s %-10s %-11s %-13s %s"
              % (r["name"], r["status"], "✔" if r["implemented"] else "·",
                 r["group"], r["evidence"]))
        if r["note"]:
            print("%-34s %-10s %-11s %-13s └ %s" % ("", "", "", "", r["note"]))
    print("\n合计 %d 条：%s" % (len(rows), summary()))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    from ..core.com import pyw, val
    app = _app()
    doc = _doc(app)
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    feats, feat = 0, None
    try:
        feat = doc.FirstFeature()
    except Exception:
        feat = None
    while feat is not None and feats < 500:
        feats += 1
        try:
            feat = pyw().Dispatch(feat).GetNextFeature()
        except Exception:
            break
    out: Dict[str, Any] = {"ok": True, "title": str(val(doc, "GetTitle", "")),
                           "type": int(val(doc, "GetType", 0) or 0), "features": feats}
    try:
        bodies = list(doc.GetBodies2(0, True) or [])
        out["bodies"] = len(bodies)
    except Exception:
        pass
    from ..verified.assembly import component_names, components
    comps = components(doc)
    if comps:
        out["components"] = len(comps)
        out["component_names"] = component_names(doc)
    if args.json:
        _dump(out)
    else:
        print("  文档 = %s  类型 = %s  特征 = %d" % (out["title"], out["type"], feats))
        if "bodies" in out:
            print("  实体 = %d" % out["bodies"])
        if "components" in out:
            print("  组件 = %d %s" % (out["components"], out["component_names"]))
    return 0


def cmd_pattern(args: argparse.Namespace) -> int:
    import math
    from ..verified.assembly import pattern_component
    doc = _doc(_app())
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = pattern_component(doc, kind=args.kind, count=args.count,
                            spacing=args.spacing,
                            angle=math.radians(args.angle_deg),
                            component_index=args.component_index,
                            dmark=args.dmark, cmark=args.cmark)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_mirror(args: argparse.Namespace) -> int:
    from ..verified.assembly import mirror_components
    doc = _doc(_app())
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = mirror_components(doc, plane_name=args.plane,
                            component_filter=args.component,
                            mirror_type=args.mirror_type)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_selftest(args: argparse.Namespace) -> int:
    """三层自检：包能 import、注册表自洽、COM 能连。"""
    checks: Dict[str, Any] = {}
    try:
        import swkit
        checks["import"] = {"ok": True, "version": swkit.__version__}
    except Exception as exc:
        checks["import"] = {"ok": False, "error": str(exc)}
    try:
        from ..registry import REGISTRY, summary
        dupes = len(REGISTRY) == 0
        checks["registry"] = {"ok": not dupes, "summary": summary()}
    except Exception as exc:
        checks["registry"] = {"ok": False, "error": str(exc)}
    try:
        from ..core.com import val
        app = _app()
        checks["com"] = {"ok": True, "revision": str(val(app, "RevisionNumber", ""))}
    except Exception as exc:
        checks["com"] = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    _dump(checks)
    return 0 if all(c.get("ok") for c in checks.values()) else 1


def _active_doc():
    app = _app()
    return _doc(app)


def cmd_bbox(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.bounding_box(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_screenshot(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.screenshot(doc, args.out, args.width, args.height)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_shell(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.shell(doc, args.thickness, args.face)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_split_line(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.split_line(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_thicken(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.thicken_surface(doc, args.thickness)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_offset_surface(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.offset_surface(doc, args.distance)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_pattern_feature(args: argparse.Namespace) -> int:
    from ..verified import part
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = part.pattern_feature(doc, kind=args.kind, count=args.count,
                               spacing=args.spacing, angle_deg=args.angle_deg)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_new_drawing(args: argparse.Namespace) -> int:
    from ..verified import drawing
    res = drawing.new_drawing(args.model, template=args.template or "",
                              view=args.view, x=args.x, y=args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_center_mark(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.center_mark(doc, x=args.x)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_centerline(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.centerline(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_symbol(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.symbol(doc, args.kind)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_surface_finish(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.surface_finish(doc, x=args.x, y=args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_note(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.note(doc, text=args.text, x=args.x, y=args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_aux_view(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.aux_view(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_section_view(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.section_view(doc, args.plane, args.offset)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_broken_view(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.broken_view(drawing.first_model_view(doc), args.orientation,
                              args.position, args.size)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_drawing_dimension(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.drawing_dimension(doc, args.x, args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_hole_table(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.hole_table(doc, args.x, args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_balloon(args: argparse.Namespace) -> int:
    from ..verified import drawing
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = drawing.balloon(doc, args.x, args.y)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_interf(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.check_interference(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_fix_component(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.fix_component(doc, component_index=args.component_index)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_show_components(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.show_all_components(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_move_component(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.move_component(doc, delta_x=args.delta_x, part_path=args.part or "")
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_explode(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.explode_assembly(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def _doc_or_none():
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
    return doc


def cmd_open_docs(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    res = ins.open_documents()
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_model_info(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.model_info(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_features(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.features(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_mass(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.mass_properties(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_bodies(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.bodies(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_custom_props(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    if args.set_value is None:
        res = ins.custom_properties(doc, args.config)
    else:
        res = ins.set_custom_property(doc, args.name, args.set_value, args.config)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_material(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.set_material(doc, args.name) if args.name else ins.material(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_rebuild(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.rebuild(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_display_mode(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.display_mode(doc, args.mode)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_list_display_states(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ins.display_states(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_dimension(args: argparse.Namespace) -> int:
    from ..verified import inspect as ins
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = (ins.set_dimension(doc, args.name, args.set_value) if args.set_value is not None
           else ins.get_dimension(doc, args.name))
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_open_doc(args: argparse.Namespace) -> int:
    from ..verified import config_io as CI
    res = CI.open_document(args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_close_doc(args: argparse.Namespace) -> int:
    from ..verified import config_io as CI
    res = CI.close_all(True) if args.all else CI.close_document(args.title, True)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_configs(args: argparse.Namespace) -> int:
    from ..verified import config_io as CI
    doc = _doc_or_none()
    if doc is None:
        return 2
    if args.add:
        res = CI.add_configuration(doc, args.add)
    elif args.activate:
        res = CI.activate_configuration(doc, args.activate)
    else:
        res = CI.list_configurations(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_save_copy(args: argparse.Namespace) -> int:
    from ..verified import config_io as CI
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = CI.save_as_copy(doc, args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_refs(args: argparse.Namespace) -> int:
    from ..verified import config_io as CI
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = CI.get_referenced_documents(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_base_flange(args: argparse.Namespace) -> int:
    from ..verified import sheet_metal as SM
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = SM.base_flange(doc, args.thickness, args.radius, args.depth)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_flat_info(args: argparse.Namespace) -> int:
    from ..verified import sheet_metal as SM
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = SM.flat_pattern_info(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_hem(args: argparse.Namespace) -> int:
    from ..verified import sheet_metal as SM
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = SM.hem(doc, args.type, 0, args.length, args.radius)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_new_part(args: argparse.Namespace) -> int:
    from ..verified import doc_ops as DO
    res = DO.create_part(args.template)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_ref_plane(args: argparse.Namespace) -> int:
    from ..verified import doc_ops as DO
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = DO.create_reference_plane(doc, args.base, args.offset)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_select(args: argparse.Namespace) -> int:
    from ..verified import doc_ops as DO
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = (DO.clear_selection(doc) if args.clear
           else DO.select_entity(doc, args.name, args.kind, args.append))
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_screenshot(args: argparse.Namespace) -> int:
    from ..verified import doc_ops as DO
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = DO.capture_screenshot(doc, args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_delete_feature(args: argparse.Namespace) -> int:
    from ..verified import doc_ops as DO
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = DO.delete_feature(doc, args.name)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_view_rotate(args: argparse.Namespace) -> int:
    from ..verified import drawing_extra as DX
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = DX.view_rotate(doc, args.angle)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_export_sheet(args: argparse.Namespace) -> int:
    from ..verified import drawing_extra as DX
    doc = _doc_or_none()
    if doc is None:
        return 2
    fn = DX.export_pdf if args.format == "pdf" else DX.export_dwg
    res = fn(doc, args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_extrude(args: argparse.Namespace) -> int:
    from ..verified import features as ft
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = ft.extrude(doc, args.depth, args.draft, args.cut)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_export(args: argparse.Namespace) -> int:
    from ..verified import io_export as IO
    fn = {"step": IO.export_step, "stl": IO.export_stl, "pdf": IO.export_pdf,
          "iges": IO.export_iges, "dxf": IO.export_dxf}[args.format]
    res = fn(args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_save(args: argparse.Namespace) -> int:
    from ..verified import io_export as IO
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = IO.save_document(doc, args.path)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_new_assembly(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    res = st.create_assembly(args.template)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_insert_component(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = st.insert_component(doc, args.part, args.x, args.y, args.z, args.fixed)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_asm_tree(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = st.assembly_tree(doc)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_suppress_component(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = st.suppress_component(doc, args.name, not args.off)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_hide_component(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = st.hide_component(doc, args.name, not args.show)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_replace_component(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = st.replace_component(doc, args.name, args.new_file)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_suppress_feature(args: argparse.Namespace) -> int:
    from ..verified import asm_state as st
    doc = _doc_or_none()
    if doc is None:
        return 2
    res = (st.unsuppress_feature(doc, args.name) if args.off
           else st.suppress_feature(doc, args.name))
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_sketch(args: argparse.Namespace) -> int:
    from ..verified import sketch_ops as so
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    a = args.action
    if a == "create":
        res = so.create_sketch(doc, args.plane)
    elif a == "edit":
        res = so.edit_sketch(doc, args.name)
    elif a == "exit":
        res = so.exit_sketch(doc)
    elif a == "line":
        res = so.line(doc, args.x1, args.y1, args.x2, args.y2)
    elif a == "circle":
        res = so.circle(doc, args.x1, args.y1, args.r)
    elif a == "rect":
        res = so.rectangle(doc, args.x1, args.y1, args.x2, args.y2)
    elif a == "arc":
        res = so.arc(doc, args.x1, args.y1, args.r, args.start, args.end)
    elif a == "ellipse":
        res = so.ellipse(doc, args.x1, args.y1, args.r, args.r2)
    elif a == "polygon":
        res = so.polygon(doc, args.x1, args.y1, args.sides, args.r)
    elif a == "spline":
        pts = [tuple(float(v) for v in p.split(",")) for p in args.points.split(";")]
        res = so.spline(doc, pts)
    else:
        res = so.centerline(doc, args.x1, args.y1, args.x2, args.y2)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_construction(args: argparse.Namespace) -> int:
    from ..verified import sketch
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = sketch.construction(doc, plane=args.plane, length=args.length)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_sketch_text(args: argparse.Namespace) -> int:
    from ..verified import sketch
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = sketch.sketch_text(doc, text=args.text, x=args.x, y=args.y, plane=args.plane)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_sketch_constraint(args: argparse.Namespace) -> int:
    from ..verified import sketch
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = sketch.sketch_constraint(doc, constraint=args.constraint, plane=args.plane)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_display_state(args: argparse.Namespace) -> int:
    from ..verified import model
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = model.activate_display_state(doc, name=args.name)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_materials(args: argparse.Namespace) -> int:
    from ..verified import model
    res = model.list_materials(directory=args.dir, name_filter=args.filter,
                               limit=args.limit, verbose=args.verbose)
    if args.json:
        _dump(res)
    else:
        d = res.get("detail") or {}
        print("  库 = %s" % (d.get("files") or []))
        print("  类别 = %s | 材料 = %s" % (d.get("categories"), d.get("materials")))
        for m in (d.get("matches") or []):
            print("    %-40s (%s)" % (m["name"], m["file"]))
    return 0 if res.get("ok") else 4


def cmd_sim(args: argparse.Namespace) -> int:
    from ..study import sim
    if args.action == "status":
        res = sim.status(args.open)
    elif args.action == "faces":
        res = sim.faces(args.open, args.limit)
    elif args.action == "list":
        res = sim.list_studies(args.open)
    elif args.action == "read":
        res = sim.read(args.open, args.study, out=args.out)
    else:
        res = sim.solve(args.open, restraint_face=args.restraint_face,
                        force_face=args.force_face, force_n=args.force,
                        material=args.material, out=args.out)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_motion(args: argparse.Namespace) -> int:
    from ..study import motion
    if args.action == "list":
        res = motion.list_studies(args.open)
    elif args.action == "status":
        res = motion.status(args.open)
    else:
        res = motion.read(args.open, study=args.study, component=args.component,
                          samples=args.samples, out=args.out, csv=args.csv)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_docs(args: argparse.Namespace) -> int:
    from ..meta import docs
    if args.action == "stats":
        res = docs.stats()
    elif args.action == "sync":
        res = docs.sync(args.dir, refresh=args.refresh)
    elif args.action == "bom":
        res = docs.bom(args.file, limit=args.limit or 200)
    elif args.action == "tables":
        res = docs.tables(args.file, limit=args.limit or 5)
    elif args.action == "show":
        res = docs.show(args.file)
    else:
        res = docs.query(prop=args.prop, folder=args.dir, ext=args.ext,
                         limit=args.limit)
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_props(args: argparse.Namespace) -> int:
    from ..meta import props as props_mod
    res = props_mod.props(args.file) if args.file else props_mod.sim_status()
    _dump(res)
    return 0 if res.get("ok") else 4


def cmd_vba(args: argparse.Namespace) -> int:
    from ..meta import vba
    res = vba.dump(args.swp) if args.action == "dump" else vba.selftest(args.swp or "")
    _dump(res)
    return 0 if res.get("ok") else 4


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="swkit", description="SolidWorks 自动化工具内核")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="连接状态 + 注册表摘要").set_defaults(func=cmd_status)

    p = sub.add_parser("registry", help="列出工具及其依据")
    p.add_argument("--status", default="", help="verified / unstable / unverified / broken")
    p.add_argument("--implemented", action="store_true", help="只看本仓库已编码、可调用的")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_registry)

    p = sub.add_parser("info", help="当前文档概览")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("pattern-component", help="组件阵列（verified）")
    p.add_argument("--kind", default="linear", choices=["linear", "circular"])
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--spacing", type=float, default=0.05, help="米")
    p.add_argument("--angle-deg", type=float, default=120.0)
    p.add_argument("--component-index", type=int, default=0)
    p.add_argument("--dmark", type=int, default=2, help="方向标记（官方=2）")
    p.add_argument("--cmark", type=int, default=1, help="组件标记（官方=1）")
    p.set_defaults(func=cmd_pattern)

    p = sub.add_parser("mirror-component", help="镜像组件（verified）")
    p.add_argument("--plane", default="前视基准面")
    p.add_argument("--component", default="", help="只镜像名称含该子串的组件")
    p.add_argument("--mirror-type", type=int, default=2,
                   help="0=包围盒中心 1=质心 2=组件原点")
    p.set_defaults(func=cmd_mirror)

    sub.add_parser("selftest", help="import/注册表/COM 三层自检").set_defaults(func=cmd_selftest)

    p = sub.add_parser("new-drawing", help="从零件建图 + 主视图（出图夹具）")
    p.add_argument("--model", required=True)
    p.add_argument("--template", default="")
    p.add_argument("--view", default="front")
    p.add_argument("--x", type=float, default=0.15)
    p.add_argument("--y", type=float, default=0.15)
    p.set_defaults(func=cmd_new_drawing)

    p = sub.add_parser("center-mark", help="中心标记（verified）")
    p.add_argument("--x", type=float, default=0.05)
    p.set_defaults(func=cmd_center_mark)

    p = sub.add_parser("centerline", help="中心线（verified）")
    p.set_defaults(func=cmd_centerline)

    p = sub.add_parser("symbol", help="基准/形位公差/焊接符号（verified）")
    p.add_argument("kind", choices=["datum", "gtol", "weld"])
    p.set_defaults(func=cmd_symbol)

    p = sub.add_parser("surface-finish", help="表面粗糙度（unverified：判据不可得）")
    p.add_argument("--x", type=float, default=0.05)
    p.add_argument("--y", type=float, default=0.05)
    p.set_defaults(func=cmd_surface_finish)

    p = sub.add_parser("note", help="注释（verified；图纸与零件通用）")
    p.add_argument("--text", required=True)
    p.add_argument("--x", type=float, default=0.05)
    p.add_argument("--y", type=float, default=0.05)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("aux-view", help="辅助视图（verified）")
    p.set_defaults(func=cmd_aux_view)

    p = sub.add_parser("section-view", help="剖视图（verified，创建后自动复位）")
    p.add_argument("--plane", default="前视基准面")
    p.add_argument("--offset", type=float, default=0.0)
    p.set_defaults(func=cmd_section_view)

    p = sub.add_parser("broken-view", help="断裂视图（verified，判据是断裂线数量）")
    p.add_argument("--orientation", type=int, default=0)
    p.add_argument("--position", type=float, default=0.05)
    p.add_argument("--size", type=float, default=0.01)
    p.set_defaults(func=cmd_broken_view)

    p = sub.add_parser("drawing-dimension", help="图纸尺寸（verified）")
    p.add_argument("--x", type=float, default=0.12)
    p.add_argument("--y", type=float, default=0.12)
    p.set_defaults(func=cmd_drawing_dimension)

    p = sub.add_parser("hole-table", help="孔表（verified；视图须先激活）")
    p.add_argument("--x", type=float, default=0.10)
    p.add_argument("--y", type=float, default=0.16)
    p.set_defaults(func=cmd_hole_table)

    p = sub.add_parser("balloon", help="自动球标（verified；需装配图 BOM）")
    p.add_argument("--x", type=float, default=0.10)
    p.add_argument("--y", type=float, default=0.16)
    p.set_defaults(func=cmd_balloon)

    p = sub.add_parser("interf", help="干涉检查（verified，count=0 也算成功）")
    p.set_defaults(func=cmd_interf)

    p = sub.add_parser("fix-component", help="固定组件（verified）")
    p.add_argument("--component-index", type=int, default=0)
    p.set_defaults(func=cmd_fix_component)

    p = sub.add_parser("show-components", help="显示全部组件（verified）")
    p.set_defaults(func=cmd_show_components)

    p = sub.add_parser("move-component", help="平移组件（verified，三轴校验）")
    p.add_argument("--delta-x", type=float, default=0.05, help="米")
    p.add_argument("--part", default="", help="临时件用的零件路径（省略则取目标件）")
    p.set_defaults(func=cmd_move_component)

    p = sub.add_parser("explode", help="自动爆炸（verified）")
    p.set_defaults(func=cmd_explode)

    p = sub.add_parser("open-docs", help="列出已打开文档（verified）")
    p.set_defaults(func=cmd_open_docs)

    p = sub.add_parser("model-info", help="当前文档信息（verified）")
    p.set_defaults(func=cmd_model_info)

    p = sub.add_parser("features", help="特征表（verified）")
    p.set_defaults(func=cmd_features)

    p = sub.add_parser("mass", help="质量属性（verified）")
    p.set_defaults(func=cmd_mass)

    p = sub.add_parser("bodies", help="实体/曲面计数（verified）")
    p.set_defaults(func=cmd_bodies)

    p = sub.add_parser("custom-props", help="自定义属性 读/写（verified）")
    p.add_argument("--config", default="")
    p.add_argument("--name", default="")
    p.add_argument("--set-value", default=None)
    p.set_defaults(func=cmd_custom_props)

    p = sub.add_parser("material", help="材料 读/写（verified）")
    p.add_argument("--name", default="", help="给名字则设置材料")
    p.set_defaults(func=cmd_material)

    p = sub.add_parser("rebuild", help="强制重建（verified）")
    p.set_defaults(func=cmd_rebuild)

    p = sub.add_parser("display-mode", help="显示模式（verified）")
    p.add_argument("mode", nargs="?", default="shaded",
                   choices=["wireframe", "hidden_lines_visible",
                            "hidden_lines_removed", "shaded"])
    p.set_defaults(func=cmd_display_mode)

    p = sub.add_parser("list-display-states", help="列显示状态（verified）")
    p.set_defaults(func=cmd_list_display_states)

    p = sub.add_parser("dimension", help="尺寸 读/改（verified，mm）")
    p.add_argument("--name", required=True)
    p.add_argument("--set-value", type=float, default=None)
    p.set_defaults(func=cmd_dimension)

    p = sub.add_parser("open-doc", help="打开文档（verified）")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_open_doc)

    p = sub.add_parser("close-doc", help="关文档/全部（verified）")
    p.add_argument("--title", default="")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_close_doc)

    p = sub.add_parser("configs", help="配置 列/加/切换（verified）")
    p.add_argument("--add", default="")
    p.add_argument("--activate", default="")
    p.set_defaults(func=cmd_configs)

    p = sub.add_parser("save-copy", help="另存副本（verified）")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_save_copy)

    p = sub.add_parser("refs", help="引用文档（verified）")
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("base-flange", help="钣金基体法兰（verified，mm）")
    p.add_argument("--thickness", type=float, default=2.0)
    p.add_argument("--radius", type=float, default=2.0)
    p.add_argument("--depth", type=float, default=30.0)
    p.set_defaults(func=cmd_base_flange)

    p = sub.add_parser("flat-info", help="展开图信息（verified）")
    p.set_defaults(func=cmd_flat_info)

    p = sub.add_parser("hem", help="钣金卷边（verified）")
    p.add_argument("--type", type=int, default=0)
    p.add_argument("--length", type=float, default=5.0)
    p.add_argument("--radius", type=float, default=0.5)
    p.set_defaults(func=cmd_hem)

    p = sub.add_parser("new-part", help="新建零件（verified）")
    p.add_argument("--template", default="")
    p.set_defaults(func=cmd_new_part)

    p = sub.add_parser("ref-plane", help="建基准面（verified，mm）")
    p.add_argument("--base", default="前视基准面")
    p.add_argument("--offset", type=float, default=50.0)
    p.set_defaults(func=cmd_ref_plane)

    p = sub.add_parser("select", help="选择/清空选择（verified）")
    p.add_argument("--name", default="")
    p.add_argument("--kind", default="PLANE")
    p.add_argument("--append", action="store_true")
    p.add_argument("--clear", action="store_true")
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("shot", help="视口截图 PNG（verified）")
    p.add_argument("--path", default="")
    p.set_defaults(func=cmd_screenshot)

    p = sub.add_parser("delete-feature", help="删除特征（verified）")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_delete_feature)

    p = sub.add_parser("view-rotate", help="旋转图纸视图（verified，度）")
    p.add_argument("--angle", type=float, default=15.0)
    p.set_defaults(func=cmd_view_rotate)

    p = sub.add_parser("export-sheet", help="图纸导出 pdf/dwg（verified）")
    p.add_argument("--format", required=True, choices=["pdf", "dwg"])
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_export_sheet)

    p = sub.add_parser("extrude", help="拉伸当前草图（verified，mm）")
    p.add_argument("--depth", type=float, default=20.0)
    p.add_argument("--draft", type=float, default=0.0)
    p.add_argument("--cut", action="store_true")
    p.set_defaults(func=cmd_extrude)

    p = sub.add_parser("export", help="导出 step/stl/pdf/iges/dxf（签名校验）")
    p.add_argument("--format", required=True, choices=["step", "stl", "pdf", "iges", "dxf"])
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("save", help="保存/另存（verified）")
    p.add_argument("--path", default="")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("new-assembly", help="新建装配（verified）")
    p.add_argument("--template", default="")
    p.set_defaults(func=cmd_new_assembly)

    p = sub.add_parser("insert-component", help="插入组件（verified，mm）")
    p.add_argument("--part", required=True)
    p.add_argument("--x", type=float, default=0.0)
    p.add_argument("--y", type=float, default=0.0)
    p.add_argument("--z", type=float, default=0.0)
    p.add_argument("--fixed", action="store_true")
    p.set_defaults(func=cmd_insert_component)

    p = sub.add_parser("asm-tree", help="装配树 + 状态位（verified）")
    p.set_defaults(func=cmd_asm_tree)

    p = sub.add_parser("suppress-component", help="抑制/解除组件（verified）")
    p.add_argument("--name", required=True)
    p.add_argument("--off", action="store_true", help="解除抑制")
    p.set_defaults(func=cmd_suppress_component)

    p = sub.add_parser("hide-component", help="隐藏/显示组件（verified）")
    p.add_argument("--name", required=True)
    p.add_argument("--show", action="store_true", help="改为显示")
    p.set_defaults(func=cmd_hide_component)

    p = sub.add_parser("replace-component", help="替换组件（verified）")
    p.add_argument("--name", required=True)
    p.add_argument("--new-file", required=True)
    p.set_defaults(func=cmd_replace_component)

    p = sub.add_parser("suppress-feature", help="抑制/解除特征（verified）")
    p.add_argument("--name", required=True)
    p.add_argument("--off", action="store_true", help="解除抑制")
    p.set_defaults(func=cmd_suppress_feature)

    p = sub.add_parser("sketch", help="草图实体（verified）：create/edit/exit/line/circle/…")
    p.add_argument("action", choices=["create", "edit", "exit", "line", "circle", "rect",
                                      "arc", "ellipse", "polygon", "spline", "centerline"])
    p.add_argument("--plane", default="前视基准面")
    p.add_argument("--name", default="", help="edit 用的草图名")
    p.add_argument("--x1", type=float, default=0.0)
    p.add_argument("--y1", type=float, default=0.0)
    p.add_argument("--x2", type=float, default=40.0)
    p.add_argument("--y2", type=float, default=25.0)
    p.add_argument("--r", type=float, default=10.0, help="半径 / 长半轴（mm）")
    p.add_argument("--r2", type=float, default=5.0, help="椭圆的短半轴（mm）")
    p.add_argument("--sides", type=int, default=6)
    p.add_argument("--start", type=float, default=0.0, help="圆弧起始角（度）")
    p.add_argument("--end", type=float, default=90.0, help="圆弧终止角（度）")
    p.add_argument("--points", default="0,0;15,20;35,10;50,0", help="样条点 用 ; 分隔")
    p.set_defaults(func=cmd_sketch)

    p = sub.add_parser("construction", help="草图构造线（verified）")
    p.add_argument("--plane", default="前视基准面")
    p.add_argument("--length", type=float, default=0.02, help="米")
    p.set_defaults(func=cmd_construction)

    p = sub.add_parser("sketch-text", help="草图文字（verified）")
    p.add_argument("--text", required=True)
    p.add_argument("--x", type=float, default=0.0)
    p.add_argument("--y", type=float, default=0.0)
    p.add_argument("--plane", default="前视基准面")
    p.set_defaults(func=cmd_sketch_text)

    p = sub.add_parser("sketch-constraint", help="草图约束（verified）")
    p.add_argument("--constraint", default="sgHORIZONTAL")
    p.add_argument("--plane", default="前视基准面")
    p.set_defaults(func=cmd_sketch_constraint)

    p = sub.add_parser("display-state", help="激活显示状态（verified）")
    p.add_argument("--name", default="")
    p.set_defaults(func=cmd_display_state)

    p = sub.add_parser("materials", help="列材料库（verified，直接解析 .sldmat）")
    p.add_argument("--dir", default="")
    p.add_argument("--filter", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_materials)

    p = sub.add_parser("bbox", help="实体包围盒（verified）")
    p.set_defaults(func=cmd_bbox)

    p = sub.add_parser("screenshot", help="存 BMP 位图（verified）")
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=1200)
    p.add_argument("--height", type=int, default=800)
    p.set_defaults(func=cmd_screenshot)

    p = sub.add_parser("shell", help="抽壳（verified）")
    p.add_argument("--thickness", type=float, default=0.002, help="米")
    p.add_argument("--face", type=int, default=-1, help="-1=自动选最大面")
    p.set_defaults(func=cmd_shell)

    p = sub.add_parser("split-line", help="分割线（verified）")
    p.set_defaults(func=cmd_split_line)

    p = sub.add_parser("thicken", help="曲面加厚（verified）")
    p.add_argument("--thickness", type=float, default=0.002, help="米")
    p.set_defaults(func=cmd_thicken)

    p = sub.add_parser("offset-surface", help="曲面偏移（verified）")
    p.add_argument("--distance", type=float, default=0.002, help="米")
    p.set_defaults(func=cmd_offset_surface)

    p = sub.add_parser("pattern-feature", help="特征阵列（verified；组件阵列请用 pattern-component）")
    p.add_argument("--kind", default="linear", choices=["linear", "circular"])
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--spacing", type=float, default=0.02, help="米")
    p.add_argument("--angle-deg", type=float, default=120.0)
    p.set_defaults(func=cmd_pattern_feature)

    p = sub.add_parser("sim", help="Simulation：status/faces/list/read/solve")
    p.add_argument("action", choices=["status", "faces", "list", "read", "solve"])
    p.add_argument("--open", default="")
    p.add_argument("--study", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--restraint-face", type=int, default=0)
    p.add_argument("--force-face", type=int, default=1)
    p.add_argument("--force", type=float, default=100.0, help="牛顿")
    p.add_argument("--material", default="")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser("motion", help="Motion：list/status/read")
    p.add_argument("action", choices=["list", "status", "read"])
    p.add_argument("--open", default="")
    p.add_argument("--study", default="")
    p.add_argument("--component", default="")
    p.add_argument("--samples", type=int, default=11)
    p.add_argument("--out", default="")
    p.add_argument("--csv", default="")
    p.set_defaults(func=cmd_motion)

    p = sub.add_parser("docs", help="DocumentMgr：stats/query/bom/tables/show/sync")
    p.add_argument("action", choices=["stats", "query", "bom", "tables", "show", "sync"])
    p.add_argument("--prop", default="", help="属性名 或 属性名=值")
    p.add_argument("--dir", default="")
    p.add_argument("--ext", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--file", default="")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("props", help="单文件属性；不给 --file 则做 Simulation 加载项自检")
    p.add_argument("--file", default="")
    p.set_defaults(func=cmd_props)

    p = sub.add_parser("vba", help="内嵌 VBA 工程：selftest/dump")
    p.add_argument("action", choices=["selftest", "dump"])
    p.add_argument("--swp", default="")
    p.set_defaults(func=cmd_vba)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":        # pragma: no cover
    sys.exit(main())
