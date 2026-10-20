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
        rows.append({"name": entry.name, "group": entry.group, "status": entry.status,
                     "api": entry.api, "evidence": entry.evidence, "note": entry.note})
    rows.sort(key=lambda r: (r["status"] != "verified", r["group"], r["name"]))
    if args.json:
        _dump({"count": len(rows), "summary": summary(), "tools": rows})
        return 0
    print("%-34s %-10s %-14s %s" % ("工具", "状态", "分组", "依据"))
    print("-" * 110)
    for r in rows:
        print("%-34s %-10s %-14s %s" % (r["name"], r["status"], r["group"], r["evidence"]))
        if r["note"]:
            print("%-34s %-10s %-14s └ %s" % ("", "", "", r["note"]))
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="swkit", description="SolidWorks 自动化工具内核")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="连接状态 + 注册表摘要").set_defaults(func=cmd_status)

    p = sub.add_parser("registry", help="列出工具及其依据")
    p.add_argument("--status", default="", help="verified / unstable / broken")
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
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":        # pragma: no cover
    sys.exit(main())
