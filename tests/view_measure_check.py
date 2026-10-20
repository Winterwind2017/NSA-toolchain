"""tests/view_measure_check.py —— 视图缩放/定向 + 面间测量

夹具：空白零件 → 前视基准面 40×25 矩形 → 拉伸 20 mm（体积 20000 mm³）

1. zoom_to_fit：Scale2 可读且 > 0
2. set_view_orientation("isometric")：Orientation 矩阵变化
3. measure_distance：前后面距离应为 **20 mm**（容差 0.2）

    python tests/view_measure_check.py
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

from swkit.core.com import pyw, val                     # noqa: E402
from swkit.verified import features as F                # noqa: E402
from swkit.verified import sketch_ops as S              # noqa: E402
from swkit.verified import view_measure as VM           # noqa: E402


def main() -> int:
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 40, 25)
    ext = F.extrude(doc, 20.0)
    print("夹具 extrude ok=%s volume=%s"
          % (ext.get("ok"), (ext.get("detail") or {}).get("volume_after_mm3")))

    body = F.bodies(doc, 0)[0]
    box = val(F.wrap(body), "GetBodyBox")
    print("包围盒(mm) =", [round(float(v) * 1000, 2) for v in box[:6]] if box else None)

    results = {}
    results["zoom"] = VM.zoom_to_fit(doc)
    results["orient"] = VM.set_view_orientation(doc, "isometric")
    # 前视基准面是 XY 平面 → 拉伸方向 Z；取 Z 两端面上的点
    zmin = float(box[2]) * 1000 if box else 0.0
    zmax = float(box[5]) * 1000 if box else 20.0
    cx = (float(box[0]) + float(box[3])) / 2 * 1000 if box else 20.0
    cy = (float(box[1]) + float(box[4])) / 2 * 1000 if box else 12.5
    results["measure"] = VM.measure_distance(
        doc, [cx, cy, zmin], [cx, cy, zmax], expected_mm=abs(zmax - zmin))

    for name, res in results.items():
        print("== %-8s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("scale_before", "scale_after", "orientation_before",
                         "orientation_after", "requested", "selected",
                         "distance_mm", "expected_mm", "p1", "p2", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
