"""从 registry 生成技能里的"能力索引"区块。

为什么：技能如果手写能力清单，迟早和代码分叉——本仓库真发生过：
`skills/solidworks-automation/SKILL.md` 里写着"其中 32 条标 `·` 的是配方已验证
但尚未编码"，而 registry 早已是 `verified_not_implemented = 0`。

所以技能里**只放生成的索引**，正文只放方法与纪律。

用法：

    python tools/gen_skill_capabilities.py          # 重写技能里的索引
    python tools/gen_skill_capabilities.py --check  # 只校验
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from swkit.registry import REGISTRY  # noqa: E402

SKILL = os.path.join(ROOT, "skills", "solidworks-automation", "SKILL.md")
BEGIN = "<!-- gen:capabilities:BEGIN -->"
END = "<!-- gen:capabilities:END -->"

# 分组的中文说明（只影响可读性，不影响校验）
GROUP_LABEL = {
    "doc": "文档级",
    "sketch": "草图",
    "feature": "特征",
    "body": "实体",
    "surface": "曲面",
    "assembly": "装配",
    "drawing": "出图",
    "sheet_metal": "钣金",
    "io": "导入导出",
    "inspect": "只读检查",
    "view": "视图",
    "study": "仿真/运动",
    "meta": "元数据/元工具",
}


def render() -> str:
    by_group = defaultdict(list)
    for e in REGISTRY.values():
        if e.status == "verified":
            by_group[e.group].append(e.name)

    total = sum(len(v) for v in by_group.values())
    lines = [
        "本表由 `tools/gen_skill_capabilities.py` 从 `src/swkit/registry.py` 生成，"
        "**不要手改**（`tests/test_offline.py::test_skill_matches_registry` 会校验）。",
        "",
        "共 **%d** 个 verified 工具。想看完整状态（含不稳/未打通/判死）：`swkit registry`。" % total,
        "",
        "| 能力族 | 工具 |",
        "|---|---|",
    ]
    for group in sorted(by_group, key=lambda g: (-len(by_group[g]), g)):
        names = sorted(by_group[group])
        label = GROUP_LABEL.get(group, group)
        lines.append("| **%s**（%d） | %s |"
                     % (label, len(names), " ".join("`%s`" % n for n in names)))
    return "\n".join(lines) + "\n"


def apply(text: str, body: str) -> str:
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        raise SystemExit("SKILL.md 缺少标记 %s / %s" % (BEGIN, END))
    return text[:i] + BEGIN + "\n" + body + text[j:]


def main() -> int:
    check = "--check" in sys.argv
    with open(SKILL, encoding="utf-8") as fh:
        text = fh.read()
    new = apply(text, render())
    if check:
        same = new.strip() == text.strip()
        print("技能能力索引一致:", same)
        if not same:
            print("（跑 python tools/gen_skill_capabilities.py 重生成）")
        return 0 if same else 4
    with open(SKILL, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("已重写技能能力索引：%s" % SKILL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
