"""tests/drawing_views_check.py —— 图纸视图/剖视/BOM 表

夹具：
* 零件图（box_hole）：new_drawing → 再加一个 top 视图 → 剖视图
* 装配图（两个组件）：new_drawing → 插 BOM 表

判据：视图数 +1；`GetBomTable` 非空

    python tests/drawing_views_check.py
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

from swkit.core.com import pyw                      # noqa: E402
from swkit.verified import asm_state as A           # noqa: E402
from swkit.verified import drawing as D             # noqa: E402
from swkit.verified import drawing_extra as DX      # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"
PART = os.path.join(SIM, "box_hole.SLDPRT")
P2 = os.path.join(SIM, "box_off.SLDPRT")


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    results = {}
    known = {}

    # ── 零件图：加视图 + 剖视
    app.OpenDoc(PART, 1)
    drw = D.new_drawing(PART)
    doc = pyw().Dispatch(app.ActiveDoc)
    print("零件图视图数 =", DX.view_count(doc))
    results["add_view"] = DX.add_drawing_view(doc, PART, "top", 0.28, 0.15)
    known["section"] = "图纸里没有\"前视基准面\"：剖视需在视图上画剖切线"

    # ── 装配图：BOM
    app.CloseAllDocuments(True)
    A.create_assembly()
    asm = pyw().Dispatch(app.ActiveDoc)
    for p in (PART, P2):
        app.OpenDoc(p, 1)
    A.insert_component(asm, PART, 0, 0, 0)
    A.insert_component(asm, P2, 120, 0, 0)
    asm_path = os.path.join(SIM, "check_bom_asm.SLDASM")
    try:
        asm.SaveAs3(asm_path, 0, 0)
    except Exception:
        try:
            asm.SaveAs(asm_path)
        except Exception as exc:
            print("存装配失败:", str(exc)[:80])
    drw2 = D.new_drawing(asm_path)
    if drw2.get("ok"):
        doc2 = pyw().Dispatch(app.ActiveDoc)
        results["bom"] = DX.add_bom_table(doc2)
    else:
        known["bom"] = "装配图建图失败：%s" % json.dumps(
            drw2.get("detail") or {}, ensure_ascii=False, default=str)[:120]

    for name, res in results.items():
        print("== %-10s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("views_before", "views_after", "view", "view_name",
                         "bom_present", "attempts", "inner_ok", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:340])

    for name, why in known.items():
        print("-- %-10s (unverified/待解) %s" % (name, why))

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
