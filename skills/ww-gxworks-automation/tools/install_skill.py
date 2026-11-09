"""把技能装到 DSH / Cursor 的 skills 目录（复制 SKILL.md + capabilities.json）。"""

from __future__ import annotations

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAME = "ww-gxworks-automation"
TARGETS = [
    pathlib.Path.home() / ".dsh" / "skills",
    pathlib.Path.home() / ".cursor" / "skills",
]


def main() -> int:
    if not (ROOT / "SKILL.md").exists():
        print("缺 SKILL.md")
        return 1
    for base in TARGETS:
        dest = base / NAME
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("SKILL.md", "capabilities.json", "capabilities.md"):
            src = ROOT / name
            if src.exists():
                shutil.copy2(src, dest / name)
        print("installed ->", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
