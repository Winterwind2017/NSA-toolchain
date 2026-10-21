"""acadkit CLI。

    acadkit status              环境自检（只附加，不启动 AutoCAD）
    acadkit env-baseline        采环境基线
    acadkit env-check           与基线比对
    acadkit registry            能力登记表（--status / --json）
    acadkit list                可实现能力清单（族 / 级别 / registry 状态）
    acadkit cap <id>            跑一个能力（动作 + 判据 + 环境自检）
    acadkit run [--only ...]    跑一组能力（默认全部）
    acadkit judges              判据清单（族 + 覆盖的 registry id）
    acadkit selftest            离线自检（不需要 AutoCAD）

退出码：0 通过 · 3 AutoCAD 未运行（只读命令）· 4 环境不合规/自检失败 ·
        5 环境漂移 · 1 用例失败
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from .. import __version__, caps, registry, status
from ..core import com, env


def _print(obj: Any, as_json: bool) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str)
          if as_json else obj)


def _parse_params(items: List[str]) -> Dict[str, Any]:
    """`--param radius=50 --param center=(0,0,0)` → dict（值尝试按 JSON 解析）。"""
    out: Dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit("--param 需要 key=value，实得 %r" % item)
        key, raw = item.split("=", 1)
        try:
            val = json.loads(raw)
        except Exception:                               # noqa: BLE001
            val = raw
        out[key.strip()] = val
    return out


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
                                        (r.get("judge") or "")[:60]))
    if problems:
        print("\n自检问题 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4
    return 0


def _join_status(ids: List[str], data: Dict[str, Any]) -> Dict[str, str]:
    by_id = {c["id"]: c for c in data["capabilities"]}
    return {i: (by_id.get(i) or {}).get("status", "unregistered") for i in ids}


def cmd_list(args: argparse.Namespace) -> int:
    data = registry.load()
    st = _join_status(list(caps.BY_ID), data)
    rows = [{"id": c.id, "family": c.family, "level": c.level,
             "title": c.title, "registry_status": st.get(c.id),
             "negative": c.is_negative,
             "params": {k: v for k, v in c.params.items()}}
            for c in caps.CAPS]
    if args.family:
        rows = [r for r in rows if r["family"] == args.family]
    if args.json:
        print(json.dumps({"total": len(rows), "rows": rows},
                         ensure_ascii=False, indent=2, default=str))
        return 0
    fams: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fams.setdefault(r["family"], []).append(r)
    print("可实现能力 %d 条（%d 族，%d 个 registry id 已覆盖）"
          % (len(rows), len(fams), len({r["id"] for r in rows}
                                       & {c["id"] for c in data["capabilities"]})))
    for fam in sorted(fams):
        print("\n[%s]" % fam)
        for r in fams[fam]:
            print("  %-30s %-7s %-4s %s"
                  % (r["id"], r["level"], "负例" if r["negative"] else "正常",
                     r["title"]))
    return 0


def _run(args: argparse.Namespace, cases, prefix: str) -> int:
    from .. import live

    payload = live.run(cases, workdir=args.workdir,
                       case_timeout=args.case_timeout, keep=args.keep,
                       prefix=prefix)
    print(live.summarize(payload))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n证据：%s" % payload.get("workdir"))
    return 0 if payload.get("ok") else 1


def cmd_cap(args: argparse.Namespace) -> int:
    from ..judges.case import Case

    cap = caps.get(args.cap_id)
    params = _parse_params(args.param)
    case: Case = cap.case(params)
    return _run(args, [case], "cap_%s" % args.cap_id.replace(".", "_"))


def cmd_run(args: argparse.Namespace) -> int:
    only = [k.strip() for k in args.only.split(",")] if args.only else None
    cases = caps.cases(only)
    if not cases:
        print("没有匹配的能力")
        return 2
    return _run(args, cases, "run")


def cmd_judges(args: argparse.Namespace) -> int:
    """判据清单：族、级别、覆盖的 registry id。"""
    data = registry.load()
    known = {c["id"] for c in data["capabilities"]}
    rows = [{"id": c.id, "family": c.family, "level": c.level,
             "negative": c.is_negative, "expect_fail": c.expect == "fail",
             "title": c.title,
             "in_registry": c.id in known} for c in caps.CAPS]
    if args.family:
        rows = [r for r in rows if r["family"] == args.family]
    problems = ["%s 不在 registry 里（判据必须有出处）" % r["id"]
                for r in rows if not r["in_registry"] and not r["negative"]
                and not r["expect_fail"]]
    if args.json:
        print(json.dumps({"families": sorted(caps.FAMILIES), "judges": rows,
                          "problems": problems}, ensure_ascii=False, indent=2))
        return 0 if not problems else 4
    fams: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fams.setdefault(r["family"], []).append(r)
    print("判据 %d 条（%d 族）" % (len(rows), len(fams)))
    for fam in sorted(fams):
        print("\n[%s]" % fam)
        for r in fams[fam]:
            print("  %-32s %-7s %s%s" % (r["id"], r["level"],
                                          "〔负例〕" if r["negative"] else "",
                                          r["title"]))
    if problems:
        print("\n自检问题 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4
    covered = {r["id"] for r in rows if r["in_registry"]}
    print("\nregistry 覆盖：%d / %d" % (len(covered), len(known)))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """离线自检：不需要 AutoCAD。"""
    checks: Dict[str, Any] = {}
    data = registry.load()
    checks["registry_loads"] = len(data["capabilities"]) > 0
    checks["registry_valid"] = not registry.validate(data)
    c = registry.counts(data)
    checks["registry_has_verified"] = c["verified"] > 0
    checks["baseline_path_writable_dir"] = bool(env.baseline_path())

    known = {x["id"] for x in data["capabilities"]}
    checks["caps_registered"] = len(caps.CAPS) > 0
    checks["caps_have_families"] = len(caps.FAMILIES) >= 8
    checks["caps_cover_registry"] = not (
        {cap.id for cap in caps.CAPS} - known - {"dim.api_missing",
                                                  "block.short_attributes"})
    checks["caps_each_family_has_one"] = all(
        ids for ids in caps.FAMILIES.values())
    checks["caps_negative_controls"] = any(cap.is_negative for cap in caps.CAPS)
    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks, "counts": c,
                      "caps": len(caps.CAPS)}, ensure_ascii=False, indent=2))
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

    s = sub.add_parser("registry", help="能力登记表")
    s.add_argument("--status", choices=list(registry.VALID_STATUS))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_registry)

    s = sub.add_parser("list", help="可实现能力清单")
    s.add_argument("--family")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("cap", help="跑一个能力（动作 + 判据）")
    s.add_argument("cap_id")
    s.add_argument("--param", action="append", default=[],
                   help="覆盖默认参数，如 --param radius=50")
    s.add_argument("--workdir")
    s.add_argument("--case-timeout", type=float, default=120.0)
    s.add_argument("--keep", action="store_true", help="跑完不退出 AutoCAD")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_cap)

    s = sub.add_parser("run", help="跑一组能力（默认全部）")
    s.add_argument("--only", default=None, help="族或 id，逗号分隔")
    s.add_argument("--workdir")
    s.add_argument("--case-timeout", type=float, default=120.0)
    s.add_argument("--keep", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("judges", help="判据清单")
    s.add_argument("--family")
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
