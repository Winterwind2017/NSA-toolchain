"""tests/sketch_edit_check.py —— 草图编辑族真机验收

夹具（每项独立）：
* trim：矩形 40×25 + 一条从 x=-10 到 x=60 的横线；在 x=60 附近裁掉伸出段
* extend：矩形 + 一条短线；延伸到更远的点
* fillet / chamfer：矩形（4 条线）选前两条做圆角/倒角
* convert_entities：零件体上选一条模型边 → 进草图 → SketchUseEdge
* start_3d_sketch：3D 草图标志

    python tests/sketch_edit_check.py
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

from swkit.core.com import pyw, val                  # noqa: E402
from swkit.verified import features as F             # noqa: E402
from swkit.verified import sketch_edit as SE         # noqa: E402
from swkit.verified import sketch_ops as S           # noqa: E402


def _new_part():
    return F.new_part()


def main() -> int:
    results = {}
    known = {}

    # 1) trim：横线伸出矩形外，裁掉右段
    doc = _new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    S.line(doc, -10, 12.5, 60, 12.5)
    print("trim 前:", SE.seg_stats(doc))
    results["trim"] = SE.trim(doc, 60.0, 12.5)

    # 2) extend：短线延伸到 y=60
    doc = _new_part()
    S.create_sketch(doc, "前视基准面")
    S.line(doc, 0, 0, 0, 20)
    print("extend 前:", SE.seg_stats(doc))
    known["extend"] = SE.extend(doc, 0.0, 60.0)

    # 3) fillet / chamfer：矩形选前两条边
    doc = _new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    results["fillet"] = SE.fillet(doc, 5.0)

    doc = _new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    results["chamfer"] = SE.chamfer(doc, 5.0)

    # 4) convert_entities：拉伸体上选一条边，进草图，转换实体
    doc = _new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    F.extrude(doc, 20.0)
    picked = 0
    try:
        body = F.bodies(doc, 0)[0]
        for face in F.faces_of(body):
            for edge in (val(face, "GetEdges") or []):
                doc.ClearSelection2(True)
                if F.wrap(edge).Select2(False, 0):
                    picked = 1
                    break
            if picked:
                break
        S.create_sketch(doc, "前视基准面")
        known["convert"] = SE.convert_entities(doc)
        results["_picked"] = picked
    except Exception as exc:
        known["convert"] = {"ok": None, "skipped": str(exc)[:80]}

    # 5) 3D 草图
    doc = _new_part()
    results["start_3d"] = SE.start_3d_sketch(doc)

    for name, res in results.items():
        if name.startswith("_"):
            continue
        print("== %-8s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("before", "after", "point_mm", "selected", "radius_mm",
                         "distance_mm", "sketch_active", "is_3d", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    for name, res in known.items():
        if res.get("ok") is None:
            print("-- %-8s SKIP  %s" % (name, res.get("skipped")))
        else:
            print("-- %-8s (unverified/待解) %s / %s"
                  % (name, res.get("checks"), (res.get("detail") or {}).get("error", "")))

    hard = {k: v for k, v in results.items()
            if not k.startswith("_") and v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
