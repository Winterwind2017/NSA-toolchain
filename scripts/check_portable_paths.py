"""仓库门禁：运行时代码里不许出现作者机器的绝对路径。

扫描范围（可用参数覆盖）：

    scripts/*.py  hub/nsa_mcp_hub/**  kernels/*/src/**

命中即退出 1，并打印 `文件:行号: 片段`。文档与真机测试脚本不在范围内
（它们本来就包含示例路径），这是有意的：门禁只守"会被别人 import / 安装"的代码。
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = (
    re.compile(r"D:\\bililive", re.I),
    re.compile(r"C:\\Users\\[^\\/\s]+\\AppData", re.I),
)
DEFAULT_SCOPES = (
    "scripts/*.py",
    "hub/nsa_mcp_hub/**",
    "kernels/*/src/**",
)


def main(argv: list[str]) -> int:
    scopes = argv[1:] or list(DEFAULT_SCOPES)
    try:
        files = subprocess.run(
            ["git", "ls-files", "--", *scopes],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print("无法列出文件（需要 git 仓库）: %s" % exc, file=sys.stderr)
        return 2

    hits: list[str] = []
    for rel in files:
        try:
            text = open(rel, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in PATTERNS:
                if pat.search(line):
                    hits.append("%s:%d: %s" % (rel, lineno, line.strip()[:120]))
                    break

    if hits:
        print("发现写死的本机路径（改用 nsa_mcp_hub.paths 或环境变量）：", file=sys.stderr)
        for hit in hits:
            print("  " + hit, file=sys.stderr)
        return 1

    print("OK：%d 个文件里没有写死的本机路径" % len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
