"""校验技能文档与 `capabilities.json` 快照一致（**不依赖 acadkit**）。

技能是给模型看的说明书：它说错，模型就会被带偏，而且不会报错。
本仓库刻意**不 import acadkit**——技能要能离线被任何机器安装与校验，
能力清单来自 `capabilities.json`（由 `tools/sync_capabilities.py` 从内核生成）。

五条规则：

1. 技能里出现的每个能力 id（`<族>.<名>`）都必须在快照里（verified 或 non_verified）；
2. 状态**不是** verified 的能力名，只允许出现在
   `<!-- allow:non-verified:BEGIN --> … END` 区块内；
3. `acadkit <cmd>` 里的 `<cmd>` 必须在快照的 `cli_commands` 里；
4. 散文里**禁止**写会漂移的数量断言（如"56 条已验证"、"58/58 通过"）——
   数量只允许出现在生成区块内；
5. SKILL.md 里的相对链接必须指向真实文件。

用法：

    python tools/check_skill.py          # 报告（有问题也退出 0）
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

ALLOW_BEGIN = "<!-- allow:non-verified:BEGIN -->"
ALLOW_END = "<!-- allow:non-verified:END -->"
GEN_BLOCKS = ("gen:capabilities",)

# `geom.py` / `docs.md` 这类文件名不是能力 id
NOT_ID_SUFFIX = {
    "py", "md", "json", "yaml", "yml", "sh", "ps1", "dll", "exe", "tlb",
    "mdb", "accdb", "lin", "pc3", "lsp", "ttf", "shx", "dwg", "dxf", "pdf",
    "txt", "log", "ini", "toml", "cfg",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load_snapshot() -> dict:
    if not os.path.isfile(SNAPSHOT):
        raise SystemExit("缺少 capabilities.json（跑 python tools/sync_capabilities.py，"
                         "或从仓库恢复）")
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
    for cid in list(snap.get("verified", {})) + list(snap.get("non_verified", {})):
        fams.add(cid.split(".", 1)[0])
    return {f for f in fams if f}


def check() -> list[str]:
    problems: list[str] = []
    snap = _load_snapshot()
    verified = set(snap.get("verified", {}))
    non_verified = set(snap.get("non_verified", {}))
    negatives = set(snap.get("negative_controls", []))
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
            name = m.group(0)
            if m.group(2) in NOT_ID_SUFFIX:
                continue
            if name not in verified and name not in non_verified and name not in negatives:
                problems.append("%s: 未知能力 `%s`（capabilities.json 里没有）"
                                % (fname, name))
                continue
            if name in non_verified and fname == "SKILL.md":
                if not any(a <= m.start() <= b for a, b in spans):
                    problems.append(
                        "%s: `%s` 状态是 %s，却出现在'别试这些'区块之外"
                        % (fname, name, snap["non_verified"][name]))

    # 规则 3
    for fname, body in texts.items():
        for m in re.finditer(r"(?<!from )acadkit\s+([a-z][a-z0-9-]*)", body):
            if m.group(1) not in cli:
                problems.append("%s: 不存在的 CLI 子命令 `acadkit %s`"
                                % (fname, m.group(1)))

    # 规则 4：散文里的数量断言
    prose = _strip_generated(text)
    count_pat = re.compile(
        r"(\d+\s*条\s*(能力|判据|用例|能力表)|"
        r"其中\s*\d+\s*条|"
        r"\d+\s*/\s*\d+\s*(通过|全绿))")
    for m in count_pat.finditer(prose):
        problems.append(
            "SKILL.md: 散文里出现会漂移的数量断言「%s」——"
            "数量只能写在生成区块里，或改成指向 `acadkit registry` / `acadkit status`"
            % m.group(0).strip())

    # 规则 5：相对链接
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
