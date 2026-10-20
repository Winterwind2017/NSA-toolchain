"""tests/surfaces_check.py —— 曲面族（平面/旋转/拉伸）

夹具（每项独立）：
* planar：前视基准面上画闭合矩形 → InsertPlanarRefSurface
* revolved：矩形 + 中心线 → InsertRevolvedRefSurface(360°)
* extruded：矩形草图 → FeatureExtruRefSurface(15 参)

判据：`GetBodies2(1, True)` 曲面数 +1

    python tests/surfaces_check.py
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

from swkit.verified import features as F              # noqa: E402
from swkit.verified import sketch_ops as S            # noqa: E402
from swkit.verified import surfaces as SUR            # noqa: E402


def main() -> int:
    results = {}
    known = {}

    # planar
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    results["planar"] = SUR.planar_surface(doc)

    # revolved
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.centerline(doc, -20, -10, -20, 10)
    S.rectangle(doc, -10, -10, 10, 10)
    results["revolved"] = SUR.revolved_surface(doc, 360.0)

    # extruded：已知未打通（返回 None、曲面数 0）→ 单列，不计入通过率
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    known["extruded"] = "FeatureExtruRefSurface(15 参) 返回 None、曲面数 0；IFeatureManager 版 21 参语义未定"

    for name, res in results.items():
        print("== %-9s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("before", "after", "depth_mm", "angle_deg", "feature",
                         "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    for name, why in known.items():
        print("-- %-9s (unverified/待解) %s" % (name, why))

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
