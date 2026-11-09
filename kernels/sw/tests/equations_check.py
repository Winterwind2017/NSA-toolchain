"""tests/equations_check.py —— 方程/全局变量/参考轴

1. list_equations：计数可读（初始 0）
2. set_global_variable("myvar", 5)：计数 0→1，Value 读回 5.0
3. list_equations：能列出这条
4. create_reference_axis：选前视+上视两个基准面 → RefAxis +1

    python tests/equations_check.py
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

from swkit.verified import equations as EQ            # noqa: E402
from swkit.verified import features as F              # noqa: E402
from swkit.verified import sketch_ops as S            # noqa: E402


def main() -> int:
    doc = F.new_part()
    results = {}
    results["list_empty"] = EQ.list_equations(doc)
    results["set_var"] = EQ.set_global_variable(doc, "myvar", 5.0)
    results["list_after"] = EQ.list_equations(doc)
    results["ref_axis"] = EQ.create_reference_axis(doc, "前视基准面", "上视基准面")

    # 方程增删（P2 转正项）：comtypes 走 IEquationMgr
    try:
        from swkit.verified import doc_ops as DO
        d2 = F.new_part()
        S.create_sketch(d2, "前视基准面")
        S.rectangle(d2, 0, 0, 40, 25)
        F.extrude(d2, 10.0)
        results["add_equation"] = DO.add_equation(d2, '"W" = 40')
        results["add_equation2"] = DO.add_equation(d2, '"H" = 25')
        results["delete_equation"] = DO.delete_equation(d2, 0)
        results["delete_equation2"] = DO.delete_equation(d2, 0)
    except Exception as _e:                          # noqa: BLE001
        results["add_equation"] = {"ok": False, "error": str(_e)[:70]}

    for name, res in results.items():
        print("== %-12s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("count", "equations", "expression", "count_before",
                         "count_after", "readback_value", "readback_equation",
                         "returned_index", "axis_before", "axis_after",
                         "selected", "returned", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:340])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
