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


def cmd_explode(args: argparse.Namespace) -> int:
    from ..verified import asm_ops
    doc = _active_doc()
    if doc is None:
        _dump({"ok": False, "error": "没有打开的文档"})
        return 2
    res = asm_ops.explode_assembly(doc)
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

    p = sub.add_parser("interf", help="干涉检查（verified，count=0 也算成功）")
    p.set_defaults(func=cmd_interf)

    p = sub.add_parser("fix-component", help="固定组件（verified）")
    p.add_argument("--component-index", type=int, default=0)
    p.set_defaults(func=cmd_fix_component)

    p = sub.add_parser("show-components", help="显示全部组件（verified）")
    p.set_defaults(func=cmd_show_components)

    p = sub.add_parser("explode", help="自动爆炸（verified）")
    p.set_defaults(func=cmd_explode)

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
