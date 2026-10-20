"""tests/bodies_check.py —— 实体级操作（缩放/删除）

夹具：两个互不相交的拉伸体（各 40×25×20，第二个在 x=100）

1. scale_body(2)：选定实体后 40×25×20 → **80×50×40**
2. delete_body(1)：实体数 **2→1**

已知未解（单列打印，不计入通过率）：
* move：`InsertMoveCopyBody2` 三种参数解释都无位移
* combine：两次相交拉伸会被自动合并成 1 个体，造不出"两个体重叠"

    python tests/bodies_check.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.verified import bodies as B                # noqa: E402
from swkit.verified import features as F              # noqa: E402
from swkit.verified import sketch_ops as S            # noqa: E402


def _two_body_part(gap: float = 100.0):
    """两个不相交的拉伸体。"""
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    F.extrude(doc, 20.0)
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, gap, 0, gap + 40, 25)
    F.extrude(doc, 20.0)
    return doc


def main() -> int:
    results = {}
    known = {
        "move": "选中实体后 InsertMoveCopyBody2 的三种参数解释都无位移（dx=0）",
        "combine": "两次相交拉伸自动合并为 1 体，需先关闭 merge 才能造出可组合的两个体",
    }

    doc = _two_body_part()
    print("缩放前:", B.body_stats(doc))
    results["scale"] = B.scale_body(doc, 2.0)

    doc = _two_body_part()
    results["delete"] = B.delete_body(doc, 1)

    for name, res in results.items():
        print("== %-8s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("factor", "size_before_mm", "size_after_mm",
                         "bodies_before", "bodies_after", "selected", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:340])

    for name, why in known.items():
        print("-- %-8s (unverified/待解) %s" % (name, why))

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
