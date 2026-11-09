#!/usr/bin/env python3
"""生成 README 的能力计数块 + `docs/CAPABILITIES.md`（两者都从代码算）。

    python tools/gen_readme_counts.py          # 改写文件
    python tools/gen_readme_counts.py --check  # 只检查是否最新（pre-push 用）

README 里被替换的部分：

    <!-- gen:counts:BEGIN -->
    ...
    <!-- gen:counts:END -->

**不要手改这两个标记之间的内容** —— 改了也会被下次生成覆盖，pre-push 会拒推。
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps as capsmod          # noqa: E402
from acadkit import registry                 # noqa: E402

BEGIN = "<!-- gen:counts:BEGIN -->"
END = "<!-- gen:counts:END -->"
CAPS_DOC = os.path.join(ROOT, "docs", "CAPABILITIES.md")


def stats():
    data = registry.load()
    c = registry.counts(data)
    known = {x["id"] for x in data["capabilities"]}
    covered = {cap.id for cap in capsmod.CAPS} & known
    negatives = [cap for cap in capsmod.CAPS
                 if cap.is_negative or cap.expect == "fail"]
    return data, c, known, covered, negatives


def counts_block() -> str:
    data, c, known, covered, negatives = stats()
    rows = [
        "| 指标 | 数字 |",
        "|---|---|",
        "| registry 能力总数 | %d |" % c["total"],
        "| verified（有判据、真机通过） | %d |" % c["verified"],
        "| usable_unjudged | %d |" % c["usable_unjudged"],
        "| pending | %d |" % c["pending"],
        "| dead（本机无官方路径） | %d |" % c["dead"],
        "| external（外部资产 / 未移植） | %d |" % c["external"],
        "| 内核实现能力（`caps`） | %d |" % len(capsmod.CAPS),
        "| caps 覆盖的 registry id | %d / %d |" % (len(covered), len(known)),
        "| 真机用例 | %d 条（含负例 %d 条） |"
        % (len(capsmod.CAPS), len(negatives)),
    ]
    return "\n".join([BEGIN] + rows + [END])


def caps_doc() -> str:
    data, c, known, covered, negatives = stats()
    by_id = {x["id"]: x for x in data["capabilities"]}
    lines = [
        "# 能力清单（自动生成）",
        "",
        "> 由 `python tools/gen_readme_counts.py` 从 `docs/registry.yaml` + "
        "`src/acadkit/caps.py` 生成，**不要手改**。",
        "",
        "`caps` 里每条能力都能真机跑一遍（动作 + 判据 + 环境自检），"
        "级别含义见 [`JUDGE_SPEC.md`](JUDGE_SPEC.md)。",
        "",
        "## 总览",
        "",
        "registry %d 条 = verified %d + usable_unjudged %d + pending %d + "
        "dead %d + external %d；内核实现 %d 条，覆盖 %d 个 registry id。"
        % (c["total"], c["verified"], c["usable_unjudged"], c["pending"],
           c["dead"], c["external"], len(capsmod.CAPS), len(covered)),
        "",
    ]
    fams = {}
    for cap in capsmod.CAPS:
        fams.setdefault(cap.family, []).append(cap)
    lines += ["## 按族", ""]
    for fam in sorted(fams):
        lines.append("- `%s`（%d）：%s"
                     % (fam, len(fams[fam]),
                        "、".join("`%s`" % x.id for x in fams[fam])))
    lines += ["", "## 明细", "",
              "| 能力 | 族 | 级别 | registry 状态 | 说明 |",
              "|---|---|---|---|---|"]
    for cap in sorted(capsmod.CAPS, key=lambda x: (x.family, x.id)):
        st = (by_id.get(cap.id) or {}).get("status", "（负例，不在 registry）")
        lines.append("| `%s` | %s | %s | %s | %s |"
                     % (cap.id, cap.family, cap.level, st, cap.title))
    lines += ["", "## 未实现的能力", "",
              "见 [`UNSUPPORTED.md`](UNSUPPORTED.md)（dead 与 external 两张表）。",
              ""]
    return "\n".join(lines)


def _rewrite(path: str, new_block: str, begin: str, end: str) -> tuple[bool, str]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if begin not in text or end not in text:
        return False, "找不到标记 %s / %s" % (begin, end)
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    out = head + new_block + tail
    changed = out != text
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
    return True, "changed" if changed else "same"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 README 计数与能力清单")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args(argv)

    readme = os.path.join(ROOT, "README.md")
    problems = 0

    if args.check:
        block = counts_block()
        with open(readme, encoding="utf-8") as fh:
            text = fh.read()
        if block not in text:
            print("README 计数块过期：跑 `python tools/gen_readme_counts.py`")
            problems += 1
        doc = caps_doc()
        if not os.path.isfile(CAPS_DOC) or open(CAPS_DOC, encoding="utf-8").read() != doc:
            print("docs/CAPABILITIES.md 过期：跑 `python tools/gen_readme_counts.py`")
            problems += 1
        return 1 if problems else 0

    ok, status = _rewrite(readme, counts_block(), BEGIN, END)
    if not ok:
        print("README 更新失败：%s" % status)
        return 1
    print("README 计数块：%s" % status)
    with open(CAPS_DOC, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(caps_doc())
    print("已写 %s" % os.path.relpath(CAPS_DOC, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
