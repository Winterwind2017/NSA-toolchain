"""核对五处数字是否一致：caps（事实来源）↔ README ↔ 矩阵 ↔ STATUS ↔ registry ↔ 技能快照。

用法：python tools/check_consistency.py [--skill <ww-nx-automation 路径>]
退出码 4 表示不一致。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nxkit import caps  # noqa: E402


def _num(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.S)
    return int(m.group(1)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default=str(ROOT.parent / "ww-nx-automation"))
    args = ap.parse_args()

    n = len(caps.CAPS)
    l4 = sum(1 for c in caps.CAPS if c.reopen)
    fams = len({c.family for c in caps.CAPS})

    problems: list[str] = []
    checked: list[str] = []

    def check(name: str, got: int | None, want: int) -> None:
        checked.append(name)
        if got != want:
            problems.append("%s = %r，应为 %d" % (name, got, want))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    check("README 能力条数", _num(r"## 能力（(\d+) 条", readme), n)
    check("README 真机通过数", _num(r"(\d+)/\1 通过", readme), n)

    matrix = (ROOT / "docs/CAPABILITY_MATRIX.md").read_text(encoding="utf-8")
    check("矩阵总计", _num(r"总计 \*\*(\d+)\*\* 条", matrix), n)
    check("矩阵 L4", _num(r"其中 \*\*(\d+)\*\* 条带 L4", matrix), l4)

    status = (ROOT / "docs/STATUS.md").read_text(encoding="utf-8")
    check("STATUS 能力数", _num(r"真机通过能力：\*\*(\d+)\*\*", status), n)
    check("STATUS L4", _num(r"带 L4（存盘→重开→复测）：\*\*(\d+)\*\*", status), l4)

    reg = (ROOT / "docs/registry.yaml").read_text(encoding="utf-8")
    check("registry verified", _num(r"verified: (\d+)", reg), n)
    check("registry L4", _num(r"L4: (\d+)", reg), l4)

    skill = Path(args.skill)
    if (skill / "capabilities.json").is_file():
        snap = json.loads((skill / "capabilities.json").read_text(encoding="utf-8"))
        counts = snap.get("counts", {})
        check("技能快照 verified", counts.get("verified"), n)
        check("技能快照 families", counts.get("families"), fams)
        pending = snap.get("pending")
        if isinstance(pending, dict):
            ids = list(pending.keys())
        else:
            ids = []
            for item in pending or []:
                if isinstance(item, dict):
                    ids.append(item.get("id"))
                elif isinstance(item, (list, tuple)):
                    ids.append(item[0])
                else:
                    ids.append(item)
        uns = (ROOT / "docs/UNSUPPORTED.md").read_text(encoding="utf-8")
        missing = [i for i in ids if ("`%s`" % i) not in uns]
        if missing:
            problems.append("快照 pending 在 UNSUPPORTED.md 里找不到：%r" % missing[:3])
    else:
        checked.append("技能快照（跳过：没有 %s）" % (skill / "capabilities.json"))

    print("核对项：%d；能力 %d 条 / L4 %d / 族 %d" % (len(checked), n, l4, fams))
    for name in checked:
        print("  · %s" % name)
    if problems:
        print("不一致：")
        for p in problems:
            print("  - " + p)
        return 4
    print("五处数字一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
