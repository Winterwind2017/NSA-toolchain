"""tests/drawing_check.py —— 出图侧真机验收

流程：从零件建 A3 图纸 + 前视图（夹具），再逐项验证：

1. `new_drawing`   —— 视图数 ≥ 2
2. `center_mark`   —— 中心标记计数 +1
3. `centerline`    —— 中心线计数 +1
4. `symbol` × 3    —— 基准 / 形位公差 / 焊接符号（对象非空 + 文本可读）
5. `surface_finish`—— 粗糙度符号计数 +1
6. `note`          —— 文本读回 + 位置读回

    python tests/drawing_check.py [--part box_hole.SLDPRT]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw                     # noqa: E402
from swkit.verified import drawing as D            # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default=os.path.join(SIM, "box_hole.SLDPRT"))
    args = ap.parse_args()
    app = pyw().Dispatch("SldWorks.Application")
    results = {}

    app.CloseAllDocuments(True)
    if app.OpenDoc(args.part, 1) is None:
        print("打不开零件：%s" % args.part)
        return 2

    # 剖视必须在零件文档上验，且要在建图之前（建图会切换 ActiveDoc）
    part_doc = pyw().Dispatch(app.ActiveDoc)
    results["section_view"] = D.section_view(part_doc, "前视基准面", 0.0)

    fx = D.new_drawing(args.part, view="front")
    results["new_drawing"] = fx
    doc = pyw().Dispatch(app.ActiveDoc)

    if fx.get("ok"):
        results["center_mark"] = D.center_mark(doc)
        results["centerline"] = D.centerline(doc)
        results["symbol_datum"] = D.symbol(doc, "datum")
        results["symbol_gtol"] = D.symbol(doc, "gtol")
        results["symbol_weld"] = D.symbol(doc, "weld")
        results["surface_finish"] = D.surface_finish(doc)
        results["note"] = D.note(doc, "技术要求：未注公差按 GB/T 1804-m")
        results["drawing_dimension"] = D.drawing_dimension(doc)
        results["hole_table"] = D.hole_table(doc)
        view = D.first_model_view(doc)
        results["broken_view"] = D.broken_view(view)
        results["aux_view"] = D.aux_view(doc)

    else:
        print("夹具失败，后续项跳过")

    for name, res in results.items():
        print("== %-16s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        detail = res.get("detail") or {}
        keep = {k: v for k, v in detail.items()
                if k in ("views", "view_name_arg", "view_created", "marks_before",
                         "marks_after", "lines_before", "lines_after", "circles",
                         "entities", "symbols_before", "symbols_after", "text",
                         "position", "attempts", "error", "title")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:420])

    passed = sum(1 for v in results.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(results), passed))
    return 0 if passed == len(results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
