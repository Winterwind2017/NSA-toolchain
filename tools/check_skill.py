"""校验技能文档与代码一致（防"技能让 Agent 去用不可用的工具"）。

技能是**给模型看的说明书**：它说错，模型就会被带偏，而且不会报错。
所以技能里的每个工具名、每条 CLI 命令都必须能在代码里找到对应物。

四条规则：

1. 技能里出现的每个 `sw_xxx` 都必须在 `registry` 里存在；
2. 状态**不是** verified 的工具名，只允许出现在
   `<!-- allow:non-verified:BEGIN --> … <!-- allow:non-verified:END -->` 区块内
   （即"别试这些"表）；这样把某条能力修好后，忘了从"别试"里删就会被抓出来；
3. `swkit <cmd>` 里的 `<cmd>` 必须是真实 CLI 子命令；
4. 散文里**禁止写会漂移的数量断言**（如"其中 32 条已验证未编码"）——
   能力数量只允许出现在生成区块里。

另外校验 SKILL.md 里的相对链接（`references/…`、`docs/…`）都指向真实文件。

用法：

    python tools/check_skill.py          # 报告
    python tools/check_skill.py --check  # 有问题时退出码 4
"""

from __future__ import annotations

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from swkit.registry import REGISTRY  # noqa: E402

SKILL_DIR = os.path.join(ROOT, "skills", "solidworks-automation")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")

ALLOW_BEGIN = "<!-- allow:non-verified:BEGIN -->"
ALLOW_END = "<!-- allow:non-verified:END -->"
GEN_BLOCKS = ("gen:capabilities",)

# 允许出现、但不在 registry 里的名字（目前没有；留作显式扩展点）
KNOWN_EXTERNAL: set[str] = set()


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_generated(text: str) -> str:
    """去掉生成区块，只校验人写的那部分。"""
    for key in GEN_BLOCKS:
        begin, end = "<!-- %s:BEGIN -->" % key, "<!-- %s:END -->" % key
        i, j = text.find(begin), text.find(end)
        if i >= 0 and j > i:
            text = text[:i] + text[j + len(end):]
    return text


def _allow_ranges(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
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


def _in_spans(idx: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= idx <= b for a, b in spans)


def check() -> list[str]:
    problems: list[str] = []
    text = _read(SKILL)
    texts = {"SKILL.md": text}
    for f in sorted(glob.glob(os.path.join(SKILL_DIR, "references", "*.md"))):
        texts[os.path.basename(f)] = _read(f)

    spans = _allow_ranges(text)

    # 规则 1 + 2
    for fname, body in texts.items():
        for m in re.finditer(r"\b(sw_[a-z0-9_]+)\b", body):
            name = m.group(1)
            if name in KNOWN_EXTERNAL:
                continue
            entry = REGISTRY.get(name)
            if entry is None:
                problems.append("%s: 未知工具 `%s`（registry 里没有）" % (fname, name))
                continue
            if entry.status != "verified" and fname == "SKILL.md":
                if not _in_spans(m.start(), spans):
                    problems.append(
                        "%s: `%s` 状态是 %s，却出现在'别试这些'区块之外"
                        % (fname, name, entry.status))

    # 规则 3
    from swkit.cli.main import build_parser

    sub = set([a for a in build_parser()._actions
               if getattr(a, "choices", None)][0].choices)
    for fname, body in texts.items():
        for m in re.finditer(r"swkit\s+([a-z][a-z0-9-]*)", body):
            cmd = m.group(1)
            if cmd not in sub:
                problems.append("%s: 不存在的 CLI 子命令 `swkit %s`" % (fname, cmd))

    # 规则 4：散文里的数量断言
    prose = _strip_generated(text)
    for m in re.finditer(r"(其中\s*\d+\s*条|\d+\s*条[^。\n]{0,12}(已验证|已编码|未编码))", prose):
        problems.append(
            "SKILL.md: 散文里出现会漂移的数量断言「%s」——"
            "数量只能写在生成区块里，或改成指向 `swkit registry`" % m.group(0).strip())

    # 链接
    for m in re.finditer(r"\]\((?!https?:)([^)#]+)\)", prose):
        target = m.group(1).strip()
        base = SKILL_DIR if target.startswith("references/") else ROOT
        if not os.path.exists(os.path.join(base, target)):
            problems.append("SKILL.md: 链接指向不存在的文件 `%s`" % target)

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("技能校验失败 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 4 if "--check" in sys.argv else 0
    print("技能校验通过：工具名、CLI 命令、数量断言、链接都与代码一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
