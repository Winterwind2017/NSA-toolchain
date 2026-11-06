# -*- coding: utf-8 -*-
"""发布前守卫：确认目标仓库在 GitHub 上是私有（不是公开）。

用法：
    python scripts/assert_private_repos.py                 # 查整个账号
    python scripts/assert_private_repos.py --only nsa-mcp-hub,solidworks-agent-kit
    python scripts/assert_private_repos.py --expect-count 22

退出码：0 = 全部私有；1 = 存在非私有仓库（会逐条列出）。

为什么需要这条：`git tag` / 「发布 vX.Y.Z」只是打标签与推提交，**不会**改变可见性；
但"发布"这个词容易让人误以为转成了公开仓库。把可见性做成一条可执行的断言，
每次发版前跑一次，就不会再靠感觉判断。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def list_repos(only: list[str] | None = None) -> list[dict]:
    result = subprocess.run(
        ["gh", "repo", "list", "--limit", "200", "--json", "name,visibility,isPrivate"],
        capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit("gh 调用失败：%s" % (result.stderr or "").strip()[:200])
    rows = json.loads(result.stdout or "[]")
    if only:
        wanted = {name.strip() for name in only if name.strip()}
        rows = [row for row in rows if row["name"] in wanted]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="确认仓库是私有的")
    parser.add_argument("--only", default="", help="逗号分隔的仓库名；省略则检查全部")
    parser.add_argument("--expect-count", type=int, default=0,
                        help="期望的仓库数量（0 = 不校验）")
    args = parser.parse_args()

    only = [name for name in args.only.split(",") if name.strip()] or None
    rows = list_repos(only)
    if not rows:
        print("没有查到仓库（gh 未登录？）")
        return 1

    public = [row for row in rows if not row.get("isPrivate")]
    print("仓库 %d 个：私有 %d，非私有 %d" % (len(rows), len(rows) - len(public), len(public)))
    for row in rows:
        mark = "ok" if row.get("isPrivate") else "!! 非私有"
        print("  %-28s %-9s %s" % (row["name"], row.get("visibility", ""), mark))

    if args.expect_count and len(rows) != args.expect_count:
        print("数量不符：期望 %d，实际 %d" % (args.expect_count, len(rows)))
        return 1
    if public:
        print("\n有 %d 个仓库不是私有：%s" % (len(public), ", ".join(r["name"] for r in public)))
        print("修法：gh repo edit Winterwind2017/<repo> --visibility private "
              "--accept-visibility-change-consequences")
        return 1
    print("\n全部私有 [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
