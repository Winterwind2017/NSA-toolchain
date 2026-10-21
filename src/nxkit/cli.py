"""nxkit 命令行：status / list / registry / cap / run / selftest。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import caps, judges, live, session


def _print_caps(items) -> None:
    print("%-24s %-9s %-8s %s" % ("id", "family", "level", "title"))
    for c in items:
        print("%-24s %-9s %-8s %s" % (c.id, c.family, c.level, c.title))


def cmd_status(args) -> int:
    ok, why = session.available()
    print("run_journal :", why if ok else "缺失")
    print("代码根      :", session.code_root())
    print("能力数      : %d（%s）" % (len(caps.CAPS), ", ".join(caps.FAMILIES)))
    if not ok:
        return 4
    return 0


def cmd_list(args) -> int:
    items = caps.list_caps(args.family)
    _print_caps(items)
    return 0


def cmd_registry(args) -> int:
    data = {
        "version": 1,
        "caps": [{"id": c.id, "family": c.family, "level": c.level,
                  "action": c.action, "params": c.params, "expect": c.expect,
                  "reopen": c.reopen, "title": c.title} for c in caps.CAPS],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _selected(args) -> list:
    if args.only:
        wanted = [x.strip() for x in args.only.split(",") if x.strip()]
        out = []
        for w in wanted:
            fam = caps.list_caps(w)
            if fam:
                out.extend(fam)
            elif w in caps.BY_ID:
                out.append(caps.BY_ID[w])
            else:
                raise SystemExit("未知能力/族：%s" % w)
        return out
    return caps.list_caps()


def cmd_run(args) -> int:
    res = live.run(_selected(args), workdir=args.workdir, timeout=args.timeout)
    print(live.summarize(res))
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["passed"] == res["total"] else 2


def cmd_cap(args) -> int:
    cap = caps.get(args.id)
    res = live.run([cap], workdir=args.workdir, timeout=args.timeout)
    print(live.summarize(res))
    rec = res["records"][0]
    print(json.dumps({"reads": rec.get("reads"), "checks": rec["checks"]},
                     ensure_ascii=False, indent=2) if args.verbose else "")
    return 0 if rec["ok"] else 2


def cmd_selftest(args) -> int:
    """离线自检：能力表自洽 + 判据逻辑（用合成读数）。"""
    problems = []
    actions_src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "runtime", "actions.py")
    actions_text = open(actions_src, encoding="utf-8").read()
    for c in caps.CAPS:
        if not c.expect:
            problems.append("%s 没有判据" % c.id)
        if ("def %s(" % c.action) not in actions_text:
            problems.append("%s 的动作 %r 未实现" % (c.id, c.action))
        if ('"%s": %s,' % (c.action, c.action)) not in actions_text:
            problems.append("%s 的动作 %r 没登记进 ACTIONS" % (c.id, c.action))
        fake = {}
        for key, val in c.expect.items():
            if isinstance(val, dict) and {"min", "max"} <= set(val):
                fake[key] = (val["min"] + val["max"]) / 2.0
            else:
                fake[key] = val
        checks = judges.compare(fake, c.expect)
        if not judges.verdict(checks):
            problems.append("%s 的判据对自身期望值不通过" % c.id)
        # 负例：故意改一个数字，必须失败
        if c.expect:
            key = next(iter(c.expect))
            bad = dict(fake)
            val = bad[key]
            bad[key] = (val * 2 + 1) if isinstance(val, (int, float)) else str(val) + "x"
            if judges.verdict(judges.compare(bad, c.expect)):
                problems.append("%s 的判据对错误读数也通过（判据无效）" % c.id)
    from . import license as lic

    if lic.summary()["readable"]:
        for cid, name in lic.missing(caps.licenses()):
            problems.append("%s 需要许可 %r，本机 .dat 里没有" % (cid, name))
    if problems:
        print("自检失败：")
        for p in problems:
            print("  -", p)
        return 4
    print("自检通过：%d 条能力，动作与判据齐全，负例都能被拒绝" % len(caps.CAPS))
    return 0


def cmd_licenses(args):
    from . import license as lic
    from . import caps as caps_mod

    info = lic.summary(args.dat)
    print("许可证文件: %s" % info["dat"])
    if not info["readable"]:
        print("读不到（跳过预检）；用 SPLM_LICENSE_SERVER 或 --dat 指定")
        return 0
    print("feature 总数: %d" % info["count"])
    needed = sorted({l for _, l in caps_mod.licenses()})
    missing = lic.missing(caps_mod.licenses())
    for name in needed:
        print("  %-18s %s" % (name, "有" if lic.has(name, args.dat) else "缺"))
    if missing:
        print("缺许可的能力 %d 条:" % len(missing))
        for cid, name in missing[:20]:
            print("  - %s 需要 %s" % (cid, name))
        return 4
    print("本机许可覆盖全部已登记能力")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nxkit", description="UG NX 2512 自动化内核")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="环境自检（不启动 NX）")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("list", help="能力清单")
    s.add_argument("--family", default=None)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("registry", help="导出能力登记表（JSON）")
    s.set_defaults(func=cmd_registry)

    s = sub.add_parser("cap", help="跑一条能力")
    s.add_argument("id")
    s.add_argument("--workdir", default=None)
    s.add_argument("--timeout", type=float, default=900.0)
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_cap)

    s = sub.add_parser("run", help="跑一组能力（默认全部，一次会话）")
    s.add_argument("--only", default=None, help="族或 id，逗号分隔")
    s.add_argument("--workdir", default=None)
    s.add_argument("--timeout", type=float, default=900.0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("licenses", help="读 .dat，检查能力所需许可")
    s.add_argument("--dat", default=None, help="SPLM .dat 路径")
    s.set_defaults(func=cmd_licenses)

    s = sub.add_parser("selftest", help="离线自检（不需要 NX）")
    s.set_defaults(func=cmd_selftest)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
