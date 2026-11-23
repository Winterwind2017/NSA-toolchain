#!/usr/bin/env python3
"""nsa —— nsa-toolchain 的统一入口（薄壳，只做转发）。

为什么需要它：现在要记 `scripts/doctor.py`、`scripts/install_skills.py --update`、
`kernels/acad/tools/fea_screen.py --case brep-cantilever ...` 三套路径与参数，
用起来不顺。这里把它们收成一组动词：

    nsa doctor                          环境诊断（包/引擎/进程/技能状态/FEA 三环）
    nsa skills status [--target DIR]    已装技能是 fresh / 旧版 / 被改 / 未装
    nsa skills install [--target DIR]   安装（--dry-run 先看）
    nsa skills update  [--target DIR]   只更新清单里已装的
    nsa skills check                    仓库内技能与注册表一致性
    nsa fea <case> [参数...]             十二种工况，参数原样透传
    nsa render --part plate ... --png x 出零件图（等轴测/三视图/SVG）
    nsa version                         版本与本仓概况

设计取舍：**用子进程转发**而不是 import。原因：
1. 每个脚本都有自己的 argparse 与退出码语义（doctor 的退出码 = 阻塞数），
   转发能原样保留；
2. 避免把 acadkit/cadquery 这些重依赖加载进 nsa 进程。
代价是多一次解释器启动（约 0.1~0.3 s），可接受。
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

SCRIPTS = os.path.join(ROOT, "scripts")
FEA = os.path.join(ROOT, "kernels", "acad", "tools", "fea_screen.py")

USAGE = """nsa —— nsa-toolchain 统一入口

用法：
  nsa doctor [--json] [--only acad,sw] [--skills-target DIR]
  nsa skills status  [--target DIR] [--json]
  nsa skills install [--target DIR] [--dry-run]
  nsa skills update  [--target DIR] [--dry-run]
  nsa skills check
  nsa fea <case> [参数...]        例如 nsa fea brep-cantilever --part plate --force 100 --png out.png
  nsa render --part plate [--views iso|three] [--svg out.svg] [--png out.png]
  nsa version

工况（nsa fea 后面第一个参数）：
  bar / cylinder / cantilever / torsion / plate /
  brep-axial / brep-cantilever / stepped / bracket / sweep / flange / combined
"""


def _run(script: str, args) -> int:
    if not os.path.isfile(script):
        print("找不到脚本：%s" % script, file=sys.stderr)
        return 2
    return subprocess.call([PY, script] + [str(a) for a in args],
                           cwd=os.path.dirname(script) or ROOT)


def _version() -> int:
    def _git(*args) -> str:
        try:
            out = subprocess.run(["git", "-C", ROOT] + list(args),
                                 capture_output=True, text=True, timeout=8)
            return (out.stdout or "").strip()
        except Exception:                                # noqa: BLE001
            return ""

    head = _git("rev-parse", "--short", "HEAD") or "（非 git 仓库）"
    when = _git("log", "-1", "--format=%cd", "--date=short")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    skills_dir = os.path.join(ROOT, "skills")
    skills = sorted(d for d in os.listdir(skills_dir)
                    if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))) \
        if os.path.isdir(skills_dir) else []
    cases = []
    if os.path.isfile(FEA):
        text = open(FEA, encoding="utf-8").read()
        start = text.find("CASES = (")
        if start >= 0:
            end = text.find(")", start)
            cases = [x.strip().strip('"\'') for x in text[start + 9:end].split(",")
                     if x.strip().strip('"\'')]
    print("nsa-toolchain")
    print("  仓库    %s" % ROOT)
    print("  版本    %s%s%s" % (head, " (%s)" % when if when else "",
                              " 分支 %s" % branch if branch else ""))
    print("  技能    %d 个：%s" % (len(skills), ", ".join(skills) or "无"))
    print("  FEA     %d 种工况" % len(cases))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if argv else 2

    cmd, rest = argv[0], argv[1:]
    if cmd == "doctor":
        return _run(os.path.join(SCRIPTS, "doctor.py"), rest)
    if cmd == "version":
        return _version()
    if cmd == "fea":
        if not rest:
            print("nsa fea 需要一个工况名；可选见 nsa help", file=sys.stderr)
            return 2
        return _run(FEA, rest)
    if cmd == "render":
        return _run(FEA, ["--case", "render"] + rest)
    if cmd == "skills":
        sub = rest[0] if rest else "status"
        tail = rest[1:]
        if sub in ("status", "list"):
            return _run(os.path.join(SCRIPTS, "install_skills.py"),
                        ["--status"] + tail)
        if sub == "install":
            return _run(os.path.join(SCRIPTS, "install_skills.py"), tail)
        if sub == "update":
            return _run(os.path.join(SCRIPTS, "install_skills.py"),
                        ["--update"] + tail)
        if sub == "check":
            return _run(os.path.join(SCRIPTS, "check_skills.py"),
                        ["--check"] + tail)
        print("未知子命令：skills %s（可用 status/install/update/check）" % sub,
              file=sys.stderr)
        return 2
    print("未知命令：%s\n" % cmd, file=sys.stderr)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
