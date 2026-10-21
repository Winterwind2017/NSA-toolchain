"""acadkit CLI。

子命令（P1 起步，后续按 registry 扩展）：

    acadkit status             环境自检（只附加，不启动 AutoCAD）
    acadkit env-baseline       采一份环境基线（写 ~/.acadkit/env_baseline.json）
    acadkit env-check          与基线比对
    acadkit registry           能力清单（--status / --json）
    acadkit judges             判据清单（四族 + registry 覆盖核对）
    acadkit selftest           离线自检（不需要 AutoCAD）

退出码：0 通过 · 3 AutoCAD 未运行（只读命令的正常结果）· 4 环境不合规 · 5 漂移
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from .. import __version__, registry, status
from ..core import com, env


def _print(obj: Any, as_json: bool) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str)
          if as_json else obj)


def cmd_status(args: argparse.Namespace) -> int:
    report, code = status.collect(compare_baseline=not args.no_baseline)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(status.render(report))
    if code == 0 and not report["snapshot"]["running"] and args.strict:
        return 3
    return code


def cmd_env_baseline(args: argparse.Namespace) -> int:
    app = com.attach_or_none()
    snap = env.snapshot(app)
    prof = env.profile_ok(snap)
    if prof is False:
        print("拒绝写基线：当前 profile 不是 %s（实际 %r）——先切回 VANILLA"
              % (env.REQUIRED_PROFILE,
                 (snap.get("variables") or {}).get("CPROFILE")))
        return 4
    if not snap["running"]:
        print("提示：AutoCAD 未运行，基线里没有系统变量；建议在 AutoCAD 打开"
              "一个空白文档后再采一次。")
    p = env.write_baseline(snap)
    print("已写基线：%s" % p)
    print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_env_check(args: argparse.Namespace) -> int:
    base = env.read_baseline()
    if base is None:
        print("没有基线，先跑 `acadkit env-baseline`")
        return 5
    app = com.attach_or_none()
    snap = env.snapshot(app)
    drift = env.diff(base, snap)
    if args.json:
        print(json.dumps({"drift": drift, "snapshot": snap},
                         ensure_ascii=False, indent=2, default=str))
    else:
        if not drift:
            print("环境与基线一致")
        else:
            print("环境漂移 %d 项：" % len(drift))
            for k, (a, b) in drift.items():
                print("  %-16s %r → %r" % (k, a, b))
    return 0 if not drift else 5


def cmd_registry(args: argparse.Namespace) -> int:
    data = registry.load()
    problems = registry.validate(data)
    rows: List[Dict[str, Any]] = data["capabilities"]
    if args.status:
        rows = [c for c in rows if c.get("status") == args.status]
    c = registry.counts(data)
    if args.json:
        print(json.dumps({"counts": c, "problems": problems, "rows": rows},
                         ensure_ascii=False, indent=2, default=str))
        return 0 if not problems else 4
    print("registry: %s" % registry.registry_path())
    print("target  : %s" % data.get("target", "?"))
    print("合计 %d：verified %d / usable_unjudged %d / pending %d / dead %d"
          % (c["total"], c["verified"], c["usable_unjudged"],
             c["pending"], c["dead"]))
    if args.status:
        print("\n[%s]" % args.status)
        for r in rows:
            print("  %-28s %-14s %s" % (r.get("id"), r.get("family"),
                                        r.get("judge", "")[:60]))
    if problems:
        print("\n自检问题 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4
    return 0


def cmd_judges(args: argparse.Namespace) -> int:
    """判据清单：四族、级别、覆盖的 registry id。"""
    from ..judges import FAMILIES, JUDGES

    known = {c["id"] for c in registry.load()["capabilities"]}
    rows: List[Dict[str, Any]] = []
    problems: List[str] = []
    for jid in sorted(JUDGES):
        meta = JUDGES[jid]
        missing = [r for r in (meta.get("registry") or []) if r not in known]
        if missing:
            problems.append("%s 指向 registry 里没有的 id: %s"
                            % (jid, ", ".join(missing)))
        if meta.get("family") not in FAMILIES:
            problems.append("%s 的族 %r 不在 FAMILIES 里" % (jid, meta.get("family")))
        rows.append({"judge": jid, "family": meta.get("family"),
                     "level": meta.get("level"),
                     "negative": bool(meta.get("negative")),
                     "registry": meta.get("registry") or [],
                     "about": meta.get("about", "")})
    if args.family:
        rows = [r for r in rows if r["family"] == args.family]
    if args.json:
        print(json.dumps({"families": sorted(FAMILIES), "judges": rows,
                          "problems": problems}, ensure_ascii=False, indent=2))
        return 0 if not problems else 4
    print("判据 %d 条（四族：%s）" % (len(rows), " / ".join(sorted(FAMILIES))))
    for fam in sorted(FAMILIES):
        print("\n[%s]" % fam)
        for r in rows:
            if r["family"] != fam:
                continue
            print("  %-32s %-6s %s%s" % (r["judge"], r["level"],
                                          "〔负例〕" if r["negative"] else "",
                                          r["about"]))
    if problems:
        print("\n自检问题 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4
    print("\nregistry 覆盖：%d 个能力 id，全部存在"
          % len({x for r in rows for x in r["registry"]}))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """离线自检：不需要 AutoCAD。"""
    from ..judges import FAMILIES, JUDGES, by_family, registry_ids

    checks: Dict[str, Any] = {}
    data = registry.load()
    checks["registry_loads"] = len(data["capabilities"]) > 0
    checks["registry_valid"] = not registry.validate(data)
    c = registry.counts(data)
    checks["registry_has_verified"] = c["verified"] > 0
    checks["baseline_path_writable_dir"] = bool(env.baseline_path())

    known = {x["id"] for x in data["capabilities"]}
    checks["judges_registered"] = len(JUDGES) > 0
    checks["judges_four_families"] = set(FAMILIES) == {"geom", "dim", "export",
                                                       "block-table"}
    checks["judges_have_registry_ids"] = not (set(registry_ids()) - known)
    checks["judges_each_family_has_one"] = all(
        by_family(f) for f in FAMILIES)
    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks, "counts": c,
                      "judges": len(JUDGES)}, ensure_ascii=False, indent=2))
    return 0 if ok else 4


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acadkit",
                                description="AutoCAD 自动化内核（%s）" % __version__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="环境自检（只附加，不启动 AutoCAD）")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-baseline", action="store_true", help="不与基线比对")
    s.add_argument("--strict", action="store_true",
                   help="AutoCAD 未运行时返回退出码 3")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("env-baseline", help="采环境基线")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_env_baseline)

    s = sub.add_parser("env-check", help="与基线比对")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_env_check)

    s = sub.add_parser("registry", help="能力清单")
    s.add_argument("--status", choices=list(registry.VALID_STATUS))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_registry)

    s = sub.add_parser("judges", help="判据清单（四族）")
    s.add_argument("--family", choices=["geom", "dim", "export", "block-table"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_judges)

    s = sub.add_parser("selftest", help="离线自检（不需要 AutoCAD）")
    s.set_defaults(func=cmd_selftest)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except com.AcadNotRunning as exc:
        print("AutoCAD 未运行：%s" % exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
