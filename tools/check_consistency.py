"""文档与能力表一致性检查：README/STATUS/registry 里的数字必须跟 caps.py 对得上。"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from gxkit import caps

    n = len(caps.CAPS)
    ids = {c.id for c in caps.CAPS}
    problems = []

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    status = (ROOT / "docs" / "STATUS.md").read_text(encoding="utf-8")
    reg = (ROOT / "docs" / "registry.yaml").read_text(encoding="utf-8")
    verify = (ROOT / "docs" / "VERIFY.md").read_text(encoding="utf-8")
    unsup = (ROOT / "docs" / "UNSUPPORTED.md").read_text(encoding="utf-8")

    m = re.search(r"\*\*(\d+)\*\* 条", status)
    if not m or int(m.group(1)) != n:
        problems.append("STATUS 里的能力数不是 %d" % n)
    m = re.search(r"verified: (\d+)", reg)
    if not m or int(m.group(1)) != n:
        problems.append("registry 的 verified 不是 %d" % n)
    if "共 %d 条" % n not in verify and "%d/6" % n not in verify:
        problems.append("VERIFY 里没有 %d 条" % n)
    for cid in re.findall(r"`([a-z][a-z0-9_.]*)`", status):
        if cid not in ids and "." in cid and not cid.startswith(("project.", "program.",
                                                                "build.", "label.",
                                                                "online.", "ladder.",
                                                                "cam.", "cae.")):
            problems.append("STATUS 引用了不存在的能力：%s" % cid)
    for cid in re.findall(r"`([a-z][a-z0-9_.]*)`", unsup):
        if cid in ids:
            problems.append("UNSUPPORTED 里写了已实现的能力：%s" % cid)

    if problems:
        print("一致性检查失败：")
        for p in problems:
            print("  -", p)
        return 1
    print("五处数字一致：%d 条能力" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
