"""校验技能文档与 `capabilities.json` 快照一致（**不依赖 nxkit**）。

五条规则：

1. 技能里出现的每个能力 id（`<族>.<名>`）都必须在快照里（verified 或 pending）；
2. pending 能力名只允许出现在 `<!-- allow:pending --> … END` 区块内；
3. `nxkit <cmd>` 里的 `<cmd>` 必须在 `cli_commands` 里；
4. 散文里禁止写会漂移的数量断言（"22 条能力"、"22/22 通过"）；
5. SKILL.md 里的相对链接必须指向真实文件。

    python tools/check_skill.py          # 报告
    python tools/check_skill.py --check  # 有问题退出 4
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "SKILL.md")
SNAPSHOT = os.path.join(ROOT, "capabilities.json")

ALLOW_BEGIN = "<!-- allow:pending:BEGIN -->"
ALLOW_END = "<!-- allow:pending:END -->"
GEN_BLOCKS = ("gen:capabilities",)

NOT_ID_SUFFIX = {
    "py", "md", "json", "yaml", "yml", "sh", "ps1", "dll", "exe", "tlb",
    "prt", "step", "stp", "igs", "iges", "dxf", "pdf", "txt", "log",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load_snapshot() -> dict:
    if not os.path.isfile(SNAPSHOT):
        raise SystemExit("缺少 capabilities.json（跑 python tools/sync_capabilities.py）")
    with open(SNAPSHOT, encoding="utf-8") as fh:
        return json.load(fh)


def _strip_generated(text: str) -> str:
    for key in GEN_BLOCKS:
        begin, end = "<!-- %s:BEGIN -->" % key, "<!-- %s:END -->" % key
        i, j = text.find(begin), text.find(end)
        if i >= 0 and j > i:
            text = text[:i] + text[j + len(end):]
    return text


def _allow_ranges(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    while True:
        i = text.find(ALLOW_BEGIN, pos)
        if i < 0:
            break
        j = text.find(ALLOW_END, i)
        if j < 0:
            break
        spans.append((i, j + len(ALLOW_END)))
        pos = j + len(ALLOW_END)
    return spans


def _families(snap: dict) -> set[str]:
    fams = set(snap.get("verified", {}).values())
    for item in snap.get("pending", []):
        fams.add(item["id"].split(".", 1)[0])
    return {f for f in fams if f}


def check() -> list[str]:
    problems: list[str] = []
    snap = _load_snapshot()
    verified = set(snap.get("verified", {}))
    pending = {p["id"] for p in snap.get("pending", [])}
    cli = set(snap.get("cli_commands", []))
    fams = _families(snap)
    id_re = re.compile(r"\b(%s)\.([a-z][a-z0-9_]*)\b"
                       % "|".join(re.escape(f) for f in sorted(fams)))

    text = _read(SKILL)
    texts = {"SKILL.md": text}
    for f in sorted(glob.glob(os.path.join(ROOT, "references", "*.md"))):
        texts[os.path.basename(f)] = _read(f)

    spans = _allow_ranges(text)

    # 规则 1 + 2
    for fname, body in texts.items():
        for m in id_re.finditer(body):
            if m.group(2) in NOT_ID_SUFFIX:
                continue
            name = m.group(0)
            if name not in verified and name not in pending:
                problems.append("%s: 未知能力 `%s`（capabilities.json 里没有）"
                                % (fname, name))
                continue
            if name in pending and fname == "SKILL.md":
                if not any(a <= m.start() <= b for a, b in spans):
                    problems.append("%s: `%s` 还是 pending，却出现在'未打通'区块之外"
                                    % (fname, name))

    # 规则 3
    for fname, body in texts.items():
        for m in re.finditer(r"(?<!import )nxkit\s+([a-z][a-z0-9-]*)", body):
            if m.group(1) not in cli:
                problems.append("%s: 不存在的 CLI 子命令 `nxkit %s`"
                                % (fname, m.group(1)))

    # 规则 4
    prose = _strip_generated(text)
    count_pat = re.compile(
        r"(\d+\s*条\s*(能力|判据|用例)|其中\s*\d+\s*条|\d+\s*/\s*\d+\s*(通过|全绿))")
    for m in count_pat.finditer(prose):
        problems.append("SKILL.md: 散文里出现会漂移的数量断言「%s」"
                        % m.group(0).strip())

    # 规则 5
    for m in re.finditer(r"\]\((?!https?:)([^)#]+)\)", prose):
        target = m.group(1).strip()
        if not os.path.exists(os.path.join(ROOT, target)):
            problems.append("SKILL.md: 链接指向不存在的文件 `%s`" % target)

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("技能校验失败 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4 if "--check" in sys.argv else 0
    print("技能校验通过：能力名、CLI 命令、数量断言、链接都与 capabilities.json 一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
