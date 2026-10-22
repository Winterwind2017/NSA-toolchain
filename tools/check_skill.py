"""技能自检：SKILL.md 里提到的能力名必须都在 capabilities.json 里，且计数一致。"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    snap = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    caps = (ROOT / "capabilities.md").read_text(encoding="utf-8")
    problems = []

    verified = snap.get("verified", {})
    n = snap["counts"]["verified"]
    if len(verified) != n:
        problems.append("capabilities.json 的 verified 数量与 counts 不一致")
    if "共 **%d** 条" % n not in caps:
        problems.append("capabilities.md 的计数不是 %d" % n)
    if "共 **%d** 条" % n not in (ROOT / "capabilities.md").read_text(encoding="utf-8"):
        problems.append("capabilities.md 计数缺失")

    for cid in re.findall(r"`([a-z][a-z0-9_]*\.[a-z0-9_.]+)`", skill):
        if cid in verified:
            continue
        if cid in snap.get("pending", {}):
            continue
        if cid in ("error", ".gx3", "project.gx3"):
            continue
        problems.append("SKILL.md 引用了未知能力：%s" % cid)

    if problems:
        print("技能校验失败：")
        for p in problems:
            print("  -", p)
        return 1
    print("技能校验通过：%d 条能力，待打通 %d 项"
          % (n, snap["counts"].get("pending", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
