"""CLI：python -m gxkit {selftest, run, caps, meta}"""

from __future__ import annotations

import argparse
import json
import pathlib

from . import caps as caps_mod


def cmd_caps(_: argparse.Namespace) -> int:
    for c in caps_mod.CAPS:
        print("%-24s %-9s %-6s %s" % (c.id, c.family, c.level, c.title))
    print("共 %d 条" % len(caps_mod.CAPS))
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    from .actions import ACTIONS

    problems = []
    for c in caps_mod.CAPS:
        if c.action not in ACTIONS:
            problems.append("%s 的动作 %s 未实现" % (c.id, c.action))
        if not c.expect:
            problems.append("%s 没有判据" % c.id)
    ids = [c.id for c in caps_mod.CAPS]
    if len(ids) != len(set(ids)):
        problems.append("cap id 有重复")
    if problems:
        print("自检失败：")
        for p in problems:
            print("  -", p)
        return 1
    print("自检通过：%d 条能力，动作与判据齐全" % len(caps_mod.CAPS))
    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    from .session import read_config, read_progress

    p = pathlib.Path(args.project)
    out = {"config": read_config(p), "progress": {k: v for k, v in read_progress(p).items()
                                                  if k != "raw"}}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .runner import run

    res = run(args.workdir, only=args.only, code=args.code, keep=args.keep,
              shuffle=args.shuffle, seed=args.seed)
    return 0 if res["passed"] == res["total"] else 1


def cmd_apply(args: argparse.Namespace) -> int:
    from .apply import apply, check_xml

    xml = pathlib.Path(args.xml)
    if args.dry:
        info = check_xml(xml)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0 if info["ok"] else 1
    out = pathlib.Path(args.out) if args.out else \
        pathlib.Path(args.workdir) / (xml.stem + ".gx3")
    return apply(xml, out, pathlib.Path(args.workdir), keep=args.keep)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gxkit", description="GX Works3 自动化内核")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest", help="离线自检")
    s.set_defaults(func=cmd_selftest)

    s = sub.add_parser("caps", help="列出能力")
    s.set_defaults(func=cmd_caps)

    s = sub.add_parser("run", help="真机跑能力")
    s.add_argument("--workdir", default=str(pathlib.Path.cwd() / "_runs" / "run1"))
    s.add_argument("--only", default=None, help="按 id 前缀或 family 过滤")
    s.add_argument("--code", default=None, help="自定义 ST 代码（\\r\\n 分隔）")
    s.add_argument("--keep", action="store_true", help="结束后不关闭 GX Works3")
    s.add_argument("--shuffle", action="store_true",
                   help="打乱能力顺序（暴露顺序依赖/状态泄漏）")
    s.add_argument("--seed", type=int, default=None, help="乱序种子（复现用）")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("meta", help="读 .gx3 的 Config 与编译日志")
    s.add_argument("project")
    s.set_defaults(func=cmd_meta)

    s = sub.add_parser("apply", help="一条命令：XML → 导入/编译/存盘/报告")
    s.add_argument("--xml", required=True, help="IEC 61131-10 XML 路径")
    s.add_argument("--out", default=None, help="目标 .gx3（默认 <workdir>/<xml 名>.gx3）")
    s.add_argument("--workdir", default=str(pathlib.Path.cwd() / "_runs" / "apply"))
    s.add_argument("--dry", action="store_true", help="只做离线预检，不开 GX Works3")
    s.add_argument("--keep", action="store_true", help="结束后不关闭 GX Works3")
    s.set_defaults(func=cmd_apply)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
