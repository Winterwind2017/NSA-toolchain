"""tests/dimxpert_check.py —— DimXpert 读取（独立 swdimxpert.tlb）

判据是**可区分**的两种结果，而不是"能调通"：

1. `create=False` 且未建 schema → `DimXpertPart` 为 None（ok=True，标记 schema_absent）
2. `create=True` → schema 名非空（本机 `模式2`）、要素/标注计数可读（0/0）
3. `AutoDimensionScheme` 已知未打通（返回 False、标注数不变）→ 单列 known

    python tests/dimxpert_check.py
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

from swkit.core.com import pyw                           # noqa: E402
from swkit.verified import dimxpert as DX                # noqa: E402
from swkit.verified import features as F                 # noqa: E402
from swkit.verified import sketch_ops as S               # noqa: E402


def main() -> int:
    F.new_part()
    doc = pyw().Dispatch(pyw().Dispatch("SldWorks.Application").ActiveDoc)
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 80, 50)
    F.extrude(doc, 12.0)

    results = {}
    results["no_schema"] = DX.info(doc, "", False)
    results["with_schema"] = DX.info(doc, "", True)
    known = {"autodim": DX.auto_dimension_scheme(doc)}

    for name, res in results.items():
        print("== %-12s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        print("   " + json.dumps(res.get("detail"), ensure_ascii=False)[:300])

    print("-- %-12s (未打通) returned=%s ann=%s" % (
        "autodim",
        (known["autodim"].get("detail") or {}).get("returned"),
        (known["autodim"].get("detail") or {}).get("annotations_after")))

    # 额外断言：两种结果的差异必须真实存在（否则判据不成立）
    diff_ok = (results["no_schema"].get("detail", {}).get("part_available") is False
               and results["with_schema"].get("detail", {}).get("part_available") is True
               and bool(results["with_schema"].get("detail", {}).get("schema_name")))
    print("\n可区分性: %s" % diff_ok)

    passed = sum(1 for v in results.values() if v.get("ok"))
    ok = passed == len(results) and diff_ok
    print("合计 %d 项，通过 %d（可区分性 %s）" % (len(results), passed, diff_ok))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
