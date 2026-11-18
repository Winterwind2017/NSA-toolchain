#!/usr/bin/env python3
"""一次性修复 `docs/registry.yaml` 的两类写入损坏（可复现，不手改数据）。

背景（2026-11-18 发现）：`docs/registry.yaml` 在生成时被写坏了两处字段格式，
内容本身没丢，但读出来的值不可用——生成器把脏值原样带进 CAPABILITIES.md / UNSUPPORTED.md：

1. `backend` 被写成了**字符数组**：
       backend: [[, c, o, m, ,,  , l, i, s, p, ]]
   PyYAML 读成 `['[', 'c', 'o', 'm', ...]`（逗号/空格被当成 flow 分隔符吃掉了）。

2. 字符串值被**多套了一层引号**（Python repr 再被 YAML 引用）：
       source: "'autocad-mcp entity.create_line / mech_build spec.geometry'"
   读出来首尾各带一个 `'`。

修法（都是确定性文本变换，逐行进行，注释与空行原样保留）：

    backend  ← 把字符还原成原文再用后端词表切分（com|lisp|headless|csg|file）
    值       ← 去掉外层那一对 `'...'`

    python tools/fix_registry_quoting.py            # 修（幂等：再跑一次无改动）
    python tools/fix_registry_quoting.py --check    # 只检查，有损坏则退出码 1
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "docs", "registry.yaml")

# 后端词表（registry 头部声明 com|lisp|headless|csg|file，另有 dim.fit_code 的纯 python 实现）
BACKENDS = ("headless", "python", "lisp", "com", "csg", "file")

RE_GARBLED_BACKEND = re.compile(r"^(\s*backend:\s*)\[\[(.*)\]\]\s*$")
RE_DOUBLE_QUOTED = re.compile(r'^(\s*[A-Za-z_]+:\s*)"\'(.*)\'"\s*$')


def _repair_backend(prefix: str, inner: str) -> str:
    """`[[, c, o, m, ,, ...]]` → `backend: [com, lisp]`。"""
    joined = re.sub(r"[\[\],\s]", "", inner)
    found, i = [], 0
    while i < len(joined):
        for tok in BACKENDS:
            if joined.startswith(tok, i):
                found.append(tok)
                i += len(tok)
                break
        else:                                   # 不认识的字符：原样保留，交给 --check 报警
            return prefix + "[[" + inner + "]]"
    if not found:
        return prefix + "[]"
    return prefix + "[" + ", ".join(found) + "]"


def repair_text(text: str) -> tuple[str, int, int]:
    out, n_backend, n_quoted = [], 0, 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        nl = line[len(body):]

        m = RE_GARBLED_BACKEND.match(body)
        if m:
            body = _repair_backend(m.group(1), m.group(2))
            n_backend += 1
            out.append(body + nl)
            continue

        m = RE_DOUBLE_QUOTED.match(body)
        if m:
            inner = m.group(2).replace('"', '\\"')
            body = '%s"%s"' % (m.group(1), inner)
            n_quoted += 1
            out.append(body + nl)
            continue

        out.append(body + nl)
    return "".join(out), n_backend, n_quoted


def count_damage(text: str) -> tuple[int, int]:
    b = sum(1 for l in text.splitlines() if RE_GARBLED_BACKEND.match(l))
    q = sum(1 for l in text.splitlines() if RE_DOUBLE_QUOTED.match(l))
    return b, q


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="修复 registry.yaml 的字符数组 / 双重引号损坏")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--path", default=REG)
    args = ap.parse_args(argv)

    with open(args.path, encoding="utf-8") as fh:
        text = fh.read()

    b, q = count_damage(text)
    if args.check:
        if b or q:
            print("registry.yaml 仍有损坏：backend 字符数组 %d 处、双重引号 %d 处" % (b, q))
            return 1
        print("registry.yaml 无此类损坏")
        return 0

    fixed, n_backend, n_quoted = repair_text(text)
    if fixed == text:
        print("无需修复（backend %d / 引号 %d）" % (b, q))
        return 0
    with open(args.path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fixed)
    print("已修 %s：backend %d 处、双重引号 %d 处"
          % (os.path.relpath(args.path, ROOT), n_backend, n_quoted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
