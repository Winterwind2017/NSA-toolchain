#!/usr/bin/env python3
"""install_hooks.py —— 把仓库里的 hooks 装到 `.git/hooks/`（每台机器跑一次）

    python scripts/install_hooks.py            # 装
    python scripts/install_hooks.py --check    # 只看装没装
    python scripts/install_hooks.py --remove   # 卸掉

Git 不会把 `.git/hooks/` 随仓库分发，所以"提醒"必须两头都有：
**仓库里带脚本**（clone 就有）+ **本脚本一键装**（跑一次就生效）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts", "hooks")
MARK = "# managed by swkit scripts/install_hooks.py"


def hooks_dir() -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                           capture_output=True, text=True, timeout=10,
                           stdin=subprocess.DEVNULL)
        gitdir = p.stdout.strip()
    except Exception:
        gitdir = ""
    if not gitdir:
        return ""
    if not os.path.isabs(gitdir):
        gitdir = os.path.join(ROOT, gitdir)
    return os.path.join(gitdir, "hooks")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()

    hd = hooks_dir()
    if not hd:
        print("不是 git 仓库（找不到 .git）", file=sys.stderr)
        return 2
    os.makedirs(hd, exist_ok=True)

    names = sorted(n for n in os.listdir(SRC) if not n.startswith("_"))
    if args.check:
        for n in names:
            dst = os.path.join(hd, n)
            state = "已装" if os.path.exists(dst) else "未装"
            print("%-12s %s" % (n, state))
        return 0

    if args.remove:
        for n in names:
            dst = os.path.join(hd, n)
            if os.path.exists(dst):
                os.remove(dst)
                print("移除 %s" % dst)
        return 0

    for n in names:
        src = os.path.join(SRC, n)
        dst = os.path.join(hd, n)
        if os.path.exists(dst):
            with open(dst, encoding="utf-8", errors="replace") as fh:
                head = fh.read(200)
            if MARK not in head:
                print("跳过 %s：已存在且不是本工具装的（避免覆盖你的 hook）" % dst)
                continue
        shutil.copy2(src, dst)
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP)
        print("装好 %s" % dst)
    print("\n完成。以后 git push 时："
          "\n  - 远端非 SSH 或 SSH key 不通 → 直接拒绝并给修法；"
          "\n  - README / UNSUPPORTED 的数字与代码不一致（生成器 --check 失败）→ 也拒绝，"
          "\n    并提示跑 tools/gen_unsupported.py + tools/gen_readme_counts.py。"
          "\n  临时绕过：SWKIT_SKIP_DOC_CHECKS=1 git push 或 git push --no-verify。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
