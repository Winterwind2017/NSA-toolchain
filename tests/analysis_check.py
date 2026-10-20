"""tests/analysis_check.py —— 装配干涉检查（P1）

夹具：两块 100×60×10 平板（box_hole / box_off），按 **mm** 定位：

1. 分开 120 mm  → 干涉 **0**
2. 重叠 20 mm   → 干涉 **1**
3. 完全重合     → 干涉 **1**
4. 不存在的 API（几何检查 / 拔模分析）必须如实报告不可用

    python tests/analysis_check.py
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

from swkit.core.com import pyw                        # noqa: E402
from swkit.verified import analysis as AN             # noqa: E402
from swkit.verified import asm_state as A             # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"
P1 = os.path.join(SIM, "box_hole.SLDPRT")
P2 = os.path.join(SIM, "box_off.SLDPRT")


def _asm(x2_mm: float):
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    A.create_assembly()
    asm = pyw().Dispatch(app.ActiveDoc)
    for p in (P1, P2):
        app.OpenDoc(p, 1)
    A.insert_component(asm, P1, 0, 0, 0)
    A.insert_component(asm, P2, x2_mm, 0, 0)      # 单位 mm
    return asm


def main() -> int:
    results = {}
    for name, x2, expect in (("separated", 120.0, 0),
                             ("overlap_20", 80.0, 1),
                             ("coincident", 0.0, 1)):
        asm = _asm(x2)
        results[name] = AN.interference_check(asm, expected=expect)
        results[name]["detail"]["x2_mm"] = x2

    results["api_availability"] = {
        "ok": (AN.geometry_check_available() is False
               and AN.draft_analysis_available() is False),
        "checks": {"geometry_check_marked_unavailable":
                   AN.geometry_check_available() is False,
                   "draft_analysis_marked_unavailable":
                   AN.draft_analysis_available() is False},
        "detail": dict(AN.UNSUPPORTED_REASONS),
    }

    for name, res in results.items():
        print("== %-18s ok=%-5s %s" % (name, res.get("ok"),
                                       json.dumps(res.get("checks"), ensure_ascii=False)))
        print("   " + json.dumps(res.get("detail"), ensure_ascii=False)[:300])

    passed = sum(1 for v in results.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(results), passed))
    return 0 if passed == len(results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
