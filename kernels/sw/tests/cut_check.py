"""tests/cut_check.py —— 切除拉伸真机验收

夹具：80×50×12 平板，顶面画两个 Ø10 圆，逐个切除。

1. blind 切除：每次体积必须**下降** π·5²·12 = **942.48 mm³**
2. 两孔后总体积 = 48000 − 2×942.48 = **46115.0 mm³**
3. through_all 切除：同样必须下降
4. 负面对照：`dir`/`flip` 组合若无效必须报 ok=False（防"静默成功"）

    python tests/cut_check.py
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

from swkit.core.com import none_dispatch, pyw, val      # noqa: E402
from swkit.verified import cuts as C                    # noqa: E402
from swkit.verified import features as F                # noqa: E402
from swkit.verified import sketch_ops as S              # noqa: E402

HOLE_AREA = 3.141592653589793 * 25.0
PLATE = 80 * 50 * 12


def _plate():
    F.new_part()
    doc = pyw().Dispatch(pyw().Dispatch("SldWorks.Application").ActiveDoc)
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 80, 50)
    F.extrude(doc, 12.0)
    return doc


def _circle_on_top(doc, cx, cy):
    doc.ClearSelection2(True)
    ok = doc.Extension.SelectByID2("", "FACE", cx / 1000, cy / 1000, 0.012,
                                   False, 0, none_dispatch(), 0)
    if not ok:
        raise RuntimeError("顶面选不中")
    doc.SketchManager.InsertSketch(True)
    S.circle(doc, cx, cy, 5.0)
    doc.SketchManager.InsertSketch(True)
    names = [str(val(f, "Name")) for f in F.iter_features(doc)]
    doc.ClearSelection2(True)
    doc.Extension.SelectByID2(names[-1], "SKETCH", 0, 0, 0, False, 0,
                              none_dispatch(), 0)
    return names[-1]


def main() -> int:
    results = {}

    # 1+2 两孔 blind
    doc = _plate()
    v0 = C._volume_mm3(doc)
    deltas = []
    for cx in (20.0, 60.0):
        _circle_on_top(doc, cx, 25.0)
        r = C.cut_extrude(doc, 12.0)
        deltas.append((r.get("detail") or {}).get("volume_delta_mm3"))
        print("  孔@%.0f ok=%s Δ=%s" % (cx, r.get("ok"), deltas[-1]))
    v2 = C._volume_mm3(doc)
    results["two_holes"] = {
        "ok": (v0 and v2 and abs(v0 - PLATE) < 1 and abs(v2 - (PLATE - 2 * HOLE_AREA * 12)) < 1.0),
        "checks": {
            "start_volume_ok": bool(v0 and abs(v0 - PLATE) < 1),
            "both_dropped": all(d is not None and d < -900 for d in deltas),
            "final_matches": bool(v2 and abs(v2 - (PLATE - 2 * HOLE_AREA * 12)) < 1.0),
        },
        "detail": {"v0": v0, "v2": v2, "deltas": deltas,
                   "expected_final": round(PLATE - 2 * HOLE_AREA * 12, 2)},
    }
    results["two_holes"]["ok"] = all(results["two_holes"]["checks"].values())

    # 3 through_all
    doc = _plate()
    v0 = C._volume_mm3(doc)
    _circle_on_top(doc, 40.0, 25.0)
    r = C.cut_extrude(doc, 0.0, through_all=True)
    v1 = C._volume_mm3(doc)
    results["through_all"] = {
        "ok": bool(r.get("ok") and v1 and v0 and v1 < v0 - 900),
        "checks": {"feature_added": (r.get("checks") or {}).get("feature_added"),
                   "volume_dropped": bool(v1 and v0 and v1 < v0 - 900)},
        "detail": {"v0": v0, "v1": v1,
                   "delta": (r.get("detail") or {}).get("volume_delta_mm3")},
    }

    # 4 负面对照：只选草图但不给 UseAutoSelect 的路径已被移除，这里验证"没草图时必须失败"
    doc = _plate()
    doc.ClearSelection2(True)
    r = C.cut_extrude(doc, 12.0)
    results["negative_no_sketch"] = {
        "ok": not r.get("ok"),
        "checks": {"refused": not r.get("ok")},
        "detail": {"error": (r.get("detail") or {}).get("error", "")[:90]},
    }

    for name, res in results.items():
        print("== %-18s ok=%-5s %s" % (name, res.get("ok"),
                                       json.dumps(res.get("checks"), ensure_ascii=False)))
        print("   " + json.dumps(res.get("detail"), ensure_ascii=False)[:260])

    passed = sum(1 for v in results.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(results), passed))
    return 0 if passed == len(results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
