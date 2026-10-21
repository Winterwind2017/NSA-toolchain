"""tests/bodies_check.py —— 实体级操作（缩放/删除/平移/组合）

夹具：两个互不相交的拉伸体（各 40×25×20，第二个在 x=100）；组合用重叠两体。

1. scale_body(2)：选定实体后 40×25×20 → **80×50×40**
2. delete_body(1)：实体数 **2→1**
3. move_body(20,-5)：包围盒位移 = 请求值；copy=copies=2 → 实体 1→3
4. combine_bodies(add)：两块重叠 20mm → 实体 2→1、体积 = 并集

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
    known = {}

    doc = _two_body_part()
    print("缩放前:", B.body_stats(doc))
    results["scale"] = B.scale_body(doc, 2.0)

    doc = _two_body_part()
    results["delete"] = B.delete_body(doc, 1)

    # 平移：单实体，判据是包围盒位移 = 请求值
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    F.extrude(doc, 10.0)
    results["move"] = B.move_body(doc, 20.0, -5.0, 0.0)

    # 复制：同一个体复制 2 份 → 实体 1→3
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    F.extrude(doc, 10.0)
    results["move_copy"] = B.move_body(doc, 60.0, 0.0, 0.0, copy=True, copies=2)

    # 组合：先复制出一个重叠 20mm 的体，再并集
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    F.extrude(doc, 10.0)
    B.move_body(doc, 20.0, 0.0, 0.0, copy=True, copies=1)
    doc = __import__("swkit.core.com", fromlist=["pyw"]).pyw().Dispatch(
        __import__("swkit.core.com", fromlist=["pyw"]).pyw().Dispatch(
            "SldWorks.Application").ActiveDoc)
    results["combine"] = B.combine_bodies(doc, "add")

    for name, res in results.items():
        print("== %-8s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("factor", "size_before_mm", "size_after_mm",
                         "bodies_before", "bodies_after", "selected", "error",
                         "delta_mm", "delta_expected_mm", "copies",
                         "volume_after_mm3", "volume_sum_before_mm3", "feature")}
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
