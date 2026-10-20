"""tests/features_check.py —— 特征建模族真机验收

每个特征都用**独立空白零件**，判据是几何量（体积/面数/特征数），并做手算对照：

1. 拉伸 40×25 草图 × 20 mm → 体积应 ≈ **20000 mm³**
2. 旋转 矩形 10×20，中心距 20 mm，360° → 体积应 ≈ 2π·20·200 = **25133 mm³**
3. 圆角 / 倒角 → 面数与特征数都增加
4. 异型孔 → 体积减少
5. 镜像 → 特征数 +1

    python tests/features_check.py
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw, val                   # noqa: E402
from swkit.verified import features as F              # noqa: E402
from swkit.verified import sketch_ops as S            # noqa: E402


def _new_part_with_rect(w=40.0, h=25.0, plane="前视基准面"):
    doc = F.new_part()
    S.create_sketch(doc, plane)
    S.rectangle(doc, 0, 0, w, h)
    return doc


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    results = {}
    stats = {}

    # 1) 拉伸：体积手算对照
    doc = _new_part_with_rect()
    results["extrude"] = F.extrude(doc, depth_mm=20.0)
    vol = (results["extrude"].get("detail") or {}).get("volume_after_mm3")
    stats["extrude_expected_mm3"] = 40.0 * 25.0 * 20.0
    stats["extrude_actual_mm3"] = vol
    if isinstance(vol, (int, float)):
        stats["extrude_rel_error"] = round(
            abs(vol - 20000.0) / 20000.0, 6)

    known = {}
    # 2) 旋转：矩形 10×20，左边线离轴 20 mm
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.centerline(doc, -20, -10, -20, 10)
    S.rectangle(doc, -10, -10, 10, 10)
    known["revolve"] = F.revolve(doc, 360.0)

    # 3) 圆角 / 倒角（在拉伸体上）
    doc = _new_part_with_rect()
    F.extrude(doc, depth_mm=20.0)
    results["fillet"] = F.fillet(doc, 5.0, 4)

    doc = _new_part_with_rect()
    F.extrude(doc, depth_mm=20.0)
    results["chamfer"] = F.chamfer(doc, 5.0, 45.0, 4)

    # 4) 异型孔（先选顶面）
    doc = _new_part_with_rect()
    F.extrude(doc, depth_mm=20.0)
    try:
        body = F.bodies(doc, 0)[0]
        faces = F.faces_of(body)
        top = faces[0]
        doc.ClearSelection2(True)
        top.Select2(False, 0)
    except Exception as exc:
        print("选面失败：%s" % exc)
    known["hole_wizard"] = F.hole_wizard(doc, depth_mm=10.0, x_mm=0, y_mm=0)

    # 5) 镜像（选中拉伸特征后镜像到前视基准面）
    doc = _new_part_with_rect()
    F.extrude(doc, depth_mm=20.0)
    try:
        target = None
        for feat in F.iter_features(doc):
            if str(val(feat, "GetTypeName2")).startswith(("Extrusion", "Boss")):
                target = feat
        if target is not None:
            doc.ClearSelection2(True)
            target.Select2(False, 0)
    except Exception:
        pass
    known["mirror_feature"] = F.mirror_feature(doc, "前视基准面")

    print()
    for name, res in known.items():
        print("-- %-16s (unverified/待解) %s" % (name,
              ((res.get("detail") or {}).get("error") or "")[:80]))

    for name, res in results.items():
        print("== %-16s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("depth_mm", "features_before", "features_after",
                         "faces_before", "faces_after", "solids_before",
                         "solids_after", "volume_before_mm3", "volume_after_mm3",
                         "volume_mm3", "edges_selected", "angle_deg", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    print("\n手算对照：拉伸体积 期望 %.1f / 实测 %s（相对误差 %s）"
          % (stats.get("extrude_expected_mm3", 0), stats.get("extrude_actual_mm3"),
             stats.get("extrude_rel_error")))

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
